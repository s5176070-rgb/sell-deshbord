@echo off
rem Start the local page. "python" on this machine resolves to the Microsoft
rem Store stub, so the interpreter is named outright.
set PY=C:\Users\97252\AppData\Local\Python\pythoncore-3.14-64\python.exe
if not exist "%PY%" set PY=python
"%PY%" "%~dp0serve.py"
