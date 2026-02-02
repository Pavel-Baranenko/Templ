import json
import os
import base64
import time
import sys
import hashlib
from decimal import Decimal, ROUND_UP
from datetime import datetime, timedelta
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, BaseLoader, Undefined
import pytz
from pytils import numeral
from bson.tz_util import FixedOffset
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class Money:
    def __init__(self, value, currency="RUB"):
        self._value = Decimal(str(value))
        self._currency = MockCurrency(currency)
        self.total_cents = int(self._value * 100)
    
    @property
    def value(self):
        return self._value
    
    @property
    def currency(self):
        return self._currency.string
    
    def __str__(self):
        return f"{self._value} {self._currency.string}"

class MockCurrency:
    def __init__(self, currency):
        self.string = currency
        self.precision = 2
        self.char = "₽" if currency == "RUB" else currency

CURRENCIES_BY_NAME = {
    "RUB": MockCurrency("RUB"),
    "USD": MockCurrency("USD"),
    "EUR": MockCurrency("EUR"),
}

MONTH_NAMES = {
    'ru': [
        'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
        'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'
    ],
    'en': [
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
    ]
}


def format_datetime(dt, format=None, tz=None, lang=None):

    return dt

def dumb_i18n(text, lang):
    if not text:
        return text
    
    if isinstance(text, dict):
        return text.get(lang, text.get('ru', ''))
    
    if isinstance(text, str):
        split_text = text.split('///')
        if lang == 'en' and len(split_text) == 2:
            return split_text[1]
        else:
            return split_text[0]
    
    return str(text)

def money_stringify(money):
    if isinstance(money, Money):
        if not money._value or money._value == 0:
            return '0'
        
        curr_id = money.currency
        curr = CURRENCIES_BY_NAME.get(curr_id)
        
        if curr and curr.char:
            return f'{money.value}{curr.char}'
        else:
            return str(money)
    
    elif isinstance(money, str):
        if ' ' in money:
            value, alfa_code = money.split(' ', 1)
        else:
            value, alfa_code = money, "RUB"
        
        try:
            if not float(value):
                return '0'
        except:
            return money
        
        curr = CURRENCIES_BY_NAME.get(alfa_code)
        
        if curr and curr.char:
            return f'{value}{curr.char}'
        else:
            return money
    
    elif isinstance(money, (int, float, Decimal)):
        if not money:
            return '0'
        
        curr = CURRENCIES_BY_NAME.get("RUB")
        return f'{money}{curr.char}' if curr else str(money)
    
    else:
        return str(money) if money else '0'

def gen_barcode(ticket, write_text=True):
    return ''

class MockRequest:
    def __init__(self, host_url):
        self.registry = MockRegistry(host_url)

class MockRegistry:
    def __init__(self, host_url):
        self.settings = MockSettings(host_url)

class MockSettings:
    def __init__(self, host_url):
        self.host_url = host_url

class MockFindTicketInfo:
    def __init__(self, discount=None):
        self.discount = discount


def render_template(template_path, data_path, output_path=None):
    """Основная функция рендеринга шаблона"""
    print(f"Рендеринг шаблона: {template_path} с данными: {data_path}")
    
    with open(data_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if 'request' in data:
        data['request'] = MockRequest(data['request']['registry']['settings']['host_url'])
    
    def process_datetime(obj, key_path):
        keys = key_path.split('.')
        current = obj
        for key in keys[:-1]:
            if key in current:
                current = current[key]
            else:
                return
        
        last_key = keys[-1]
        if last_key in current and isinstance(current[last_key], str):
            try:
                date_str = current[last_key]
                
                if date_str.endswith('Z'):
                    date_str = date_str[:-1] + '+00:00'
                
                dt = datetime.fromisoformat(date_str)
                
                if dt.tzinfo is not None:
                    from datetime import timezone as dt_timezone
                    if isinstance(dt.tzinfo, dt_timezone):
                        dt = dt.astimezone(pytz.UTC)
                    else:
                        pass
                
                current[last_key] = dt
            except Exception as e:
                pass
    
    datetime_fields = [
        'order.created_at',
        'order.event.lifetime.start',
        'order.event.lifetime.end'
    ]
    
    for field in datetime_fields:
        process_datetime(data, field)
    
    if 'ticket_price' in data and data['ticket_price'] is not None:
        data['ticket_price'] = Money(data['ticket_price'], "RUB")
    
    if 'discount' in data and data['discount'] is not None:
        data['ticket_discount'] = Money(data['discount'], "RUB")
    
    if 'ticket' in data:
        if 'id' not in data['ticket']:
            data['ticket']['id'] = 1
        
        if 'order' not in data['ticket']:
            data['ticket']['order'] = {}
        
        if 'vars' not in data['ticket']['order']:
            data['ticket']['order']['vars'] = {}
        
        def create_find_ticket_info(discount_value):
            def find_ticket_info(ticket_id):
                if ticket_id == data['ticket'].get('id'):
                    return MockFindTicketInfo(discount_value)
                return MockFindTicketInfo(None)
            return find_ticket_info
        
        discount_value = data.get('ticket_discount')
        data['ticket']['order']['vars']['find_ticket_info'] = create_find_ticket_info(discount_value)
    
    template_dir = os.path.dirname(template_path)
    template_file = os.path.basename(template_path)
    
    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=False,
        undefined=Undefined  
    )
    
    filters = [
        'format_datetime',
        'dumb_i18n',
        'money_stringify',
        'gen_barcode'
    ]
    
    for filter_name in filters:
        env.filters[filter_name] = globals()[filter_name]
    
    template = env.get_template(template_file)
    
    try:
        rendered = template.render(**data)
    except Exception as e:
        print(f"Ошибка при рендеринге: {e}")
        raise
    
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(rendered)
        print(f"Результат сохранен в: {output_path}")
        return output_path
    else:
        print(rendered[:500] + "..." if len(rendered) > 500 else rendered)
        return rendered


class TemplateChangeHandler(FileSystemEventHandler):
    """Обработчик изменений файлов"""
    
    def __init__(self, template_path, data_path, output_path=None):
        self.template_path = template_path
        self.data_path = data_path
        self.output_path = output_path
        self.last_hash = None
        
        # Первоначальный рендеринг
        self.render_on_change()
    
    def get_file_hash(self, filepath):
        """Получить хеш файла для отслеживания изменений"""
        try:
            with open(filepath, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception as e:
            return None
    
    def render_on_change(self):
        """Выполнить рендеринг при изменении файлов"""
        try:
            render_template(self.template_path, self.data_path, self.output_path)
            current_hash = self.get_file_hash(self.template_path)
            current_data_hash = self.get_file_hash(self.data_path)
            self.last_hash = (current_hash, current_data_hash)
            print(f"Шаблон успешно обновлен в {datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"Ошибка при рендеринге: {e}")
    
    def on_modified(self, event):
        """Обработчик события изменения файла"""
        if not event.is_directory:
            # Проверяем, изменился ли наш файл шаблона или данных
            template_changed = event.src_path == os.path.abspath(self.template_path)
            data_changed = event.src_path == os.path.abspath(self.data_path)
            
            if template_changed or data_changed:
                # Ждем немного, чтобы файл был полностью записан
                time.sleep(0.1)
                
                # Получаем текущие хеши
                current_template_hash = self.get_file_hash(self.template_path)
                current_data_hash = self.get_file_hash(self.data_path)
                
                # Проверяем, действительно ли изменился контент
                last_template_hash, last_data_hash = self.last_hash if self.last_hash else (None, None)
                
                if (template_changed and current_template_hash != last_template_hash) or \
                   (data_changed and current_data_hash != last_data_hash):
                    print(f"\n{'='*50}")
                    print(f"Обнаружено изменение в: {os.path.basename(event.src_path)}")
                    print(f"{'='*50}")
                    self.render_on_change()


def watch_and_render(template_path, data_path, output_path=None):
    """
    Запустить наблюдение за файлами и автоматический рендеринг
    при изменениях
    """
    print(f"Запуск наблюдения за файлами...")
    print(f"Шаблон: {template_path}")
    print(f"Данные: {data_path}")
    if output_path:
        print(f"Выходной файл: {output_path}")
    print(f"Нажмите Ctrl+C для остановки\n")
    
    # Создаем обработчик событий
    event_handler = TemplateChangeHandler(template_path, data_path, output_path)
    
    # Создаем наблюдатель
    observer = Observer()
    
    # Добавляем наблюдение за директориями
    template_dir = os.path.dirname(os.path.abspath(template_path))
    data_dir = os.path.dirname(os.path.abspath(data_path))
    
    # Наблюдаем за директориями обоих файлов
    observer.schedule(event_handler, template_dir, recursive=False)
    if template_dir != data_dir:
        observer.schedule(event_handler, data_dir, recursive=False)
    
    # Запускаем наблюдатель
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nОстановка наблюдения...")
        observer.stop()
    
    observer.join()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    
    parser.add_argument('template', help='Путь к файлу шаблона .jinja2')
    parser.add_argument('--data', default='content.json', help='Путь к файлу с данными (по умолчанию: content.json)')
    parser.add_argument('--output', '-o', help='Путь для сохранения результата')
    parser.add_argument('--watch', '-w', action='store_true', help='Включить наблюдение за изменениями файлов')
    
    args = parser.parse_args()
    
    try:
        if args.watch:
            watch_and_render(args.template, args.data, args.output)
        else:
            result = render_template(args.template, args.data, args.output)
            if result and args.output:
                print(f"Шаблон сохранен")
           
    except FileNotFoundError as e:
        print(f"Ошибка: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Ошибка: {e}")
        sys.exit(1)