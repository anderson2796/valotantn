# Guía de Despliegue - Valorant Stats System

Esta guía explica cómo subir el sistema a un servidor funcional de forma gratuita, asegurando la privacidad de los datos y la persistencia de la base de datos.

## 1. Configuración de la Base de Datos (Neon.tech)

Como Render usa un sistema de archivos efímero (se borra al reiniciar), usaremos **Neon** para tener una base de datos PostgreSQL persistente y gratuita.

1. Regístrate en [Neon.tech](https://neon.tech/).
2. Crea un nuevo proyecto llamado `valorantn`.
3. En el Tab de **Dashboard**, copia la **Connection String** (ejemplo: `postgresql://user:password@host/dbname?sslmode=require`).
4. Guarda esta URL, la necesitaremos en Render.

## 2. Preparación del Código

Asegúrate de que tu repositorio tenga la siguiente estructura básica en la carpeta `backend/`:
- `server.py`: El archivo principal (ya actualizado con soporte para Postgres y cifrado).
- `requirements.txt`: Lista de dependencias (ya actualizada).

## 3. Despliegue en Render (Servidor Backend)

1. Crea una cuenta en [Render.com](https://render.com/).
2. Haz clic en **New +** y selecciona **Web Service**.
3. Conecta tu repositorio de GitHub.
4. Configura el servicio:
   - **Name**: `valorantn-backend`
   - **Environment**: `Python`
   - **Root Directory**: `backend` (o déjalo vacío si el código está en la raíz)
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn server:app`
5. **Variables de Entorno (IMPORTANTE)**:
   Ve a la pestaña **Environment** y añade:
   - `DATABASE_URL`: La URL que copiaste de Neon.
   - `SECRET_KEY`: Una cadena larga y aleatoria para los tokens JWT.
   - `MASTER_ENCRYPTION_KEY`: Una frase secreta larga (ej: `mi_super_secreto_valorant_2024`). **No la pierdas**, o no podrás desencriptar los correos existentes.
   - `PYTHON_VERSION`: `3.10.0` (o superior).

## 4. Despliegue del Frontend (HTML/JS/CSS)

Puedes subir el frontend a Render como un **Static Site** o a **Vercel/Netlify**.

1. En Render, selecciona **New +** -> **Static Site**.
2. Conecta el mismo repositorio.
3. **Build Command**: (Déjalo vacío si no usas frameworks como React).
4. **Publish Directory**: `.` (La raíz donde está el `index.html`).
5. **Configuración de la API**:
   En tu archivo `app.js` local, asegúrate de que la URL de la API apunte a tu nueva URL de Render (ej: `https://valorantn-backend.onrender.com`).

---

## Preguntas Frecuentes

### ¿Por qué cifrar los correos y cuentas?
Para cumplir con tu solicitud de privacidad. Ni siquiera el administrador de la base de datos podrá leer los correos o las etiquetas de las cuentas de Valorant sin la `MASTER_ENCRYPTION_KEY`.

### ¿Se pierden los datos al reiniciar el servidor?
No. Al usar **Neon (PostgreSQL)**, los datos están en la nube de forma independiente al servidor de Render.

### ¿Qué pasa con las cuentas antiguas en SQLite?
Esta actualización está pensada para un despliegue limpio. Si deseas migrar datos locales, deberías exportarlos manualmente a la nueva base de datos de Neon.
