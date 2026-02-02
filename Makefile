.PHONY: render open clean

# Рендерить шаблон
render:
	python render_jinja.py ticket.jinja2 --output output.html --watch

# Открыть в браузере
open:
	python render_jinja.py ticket.jinja2 --browser

# Быстрый просмотр в терминале
preview:
	python render_jinja.py ticket.jinja2

# Очистить сгенерированные файлы
clean:
	rm -f output.html
	rm -f /tmp/tmp*.html