# Guía de Inicio Rápido (Comandos Exactos)

Copia y pega estos comandos en tu **PowerShell** para iniciar el sistema:

## Paso 1: Ir a la carpeta del proyecto e iniciar el Servidor
Copia y pega todo este bloque en PowerShell y presiona **Enter**:

```powershell
cd "c:\Users\Anderson\Desktop\Valorant html\backend"
python server.py
```

> [!IMPORTANT]
> **No cierres esa ventana de PowerShell**. El servidor debe mantenerse corriendo para que la página web pueda mostrar tus estadísticas.

## Paso 2: Abrir la aplicación web
Una vez que el servidor esté listo (verás un mensaje de `Running on http://127.0.0.1:5000`), abre el navegador y pega esta ruta en la barra de direcciones:

```text
c:\Users\Anderson\Desktop\Valorant html\index.html
```

---

### Si el comando `python` no funciona, intenta con este:
```powershell
cd "c:\Users\Anderson\Desktop\Valorant html\backend"
py server.py
```

### Si te faltan dependencias, ejecuta esto:
```powershell
cd "c:\Users\Anderson\Desktop\Valorant html\backend"
pip install -r requirements.txt
```
