@echo off
cd /d "%~dp0"
echo Abriendo la Suite administrativa de Gio Group en tu navegador...
echo No cierres esta ventana mientras uses la app.
py -3.12 -m streamlit run app.py --browser.gatherUsageStats false
pause
