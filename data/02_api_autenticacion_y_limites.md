# Andes Pay — Guía de la API: Autenticación, Límites y Webhooks

> Documento técnico ficticio creado como dataset de ejemplo para el sistema RAG.
> Versión de la API: v2.

## 1. Entornos

Andes Pay ofrece dos entornos completamente aislados:

- **Sandbox:** `https://sandbox.api.andespay.example/v2` — para pruebas. Las tarjetas de prueba empiezan con `4000 0000`. Ningún cobro mueve dinero real.
- **Producción:** `https://api.andespay.example/v2` — requiere tener la cuenta verificada (ver la guía de onboarding y KYC).

Las credenciales de un entorno no funcionan en el otro.

## 2. Autenticación

Todas las llamadas se autentican con una **API key secreta** enviada en el encabezado:

```
Authorization: Bearer sk_live_xxxxxxxxx
```

- Las claves de sandbox empiezan con `sk_test_` y las de producción con `sk_live_`.
- Además existe una **clave pública** (`pk_live_` / `pk_test_`) que solo sirve para tokenizar tarjetas desde el frontend. Nunca debe usarse la clave secreta en el navegador ni en una app móvil.
- Las claves se pueden **rotar** desde el panel en Configuración → Desarrolladores. Al rotar, la clave anterior sigue funcionando durante **24 horas** para permitir un despliegue sin cortes, y luego se revoca.

### 2.1 Idempotencia

Para evitar cobros duplicados ante reintentos de red, todas las peticiones `POST` aceptan el encabezado `Idempotency-Key`. Andes Pay guarda la respuesta asociada a cada clave durante **24 horas**: si llega la misma clave con el mismo cuerpo, devuelve la respuesta original sin volver a procesar el cobro. Si llega la misma clave con un cuerpo distinto, responde `409 Conflict`.

## 3. Límites de uso (rate limits)

Los límites se aplican por cuenta y por entorno, en ventanas deslizantes de un minuto:

| Plan | Peticiones por minuto | Ráfaga máxima |
|------|-----------------------|---------------|
| Inicial | 100 | 20 por segundo |
| Pro | 600 | 50 por segundo |
| Enterprise | 3.000 | 200 por segundo |

En sandbox el límite es de **50 peticiones por minuto** para todos los planes.

Cuando se supera el límite, la API responde **`429 Too Many Requests`** e incluye el encabezado `Retry-After` con la cantidad de segundos que hay que esperar. Cada respuesta también incluye `X-RateLimit-Remaining`, con las peticiones restantes en la ventana actual.

Recomendación: implementar reintentos con *backoff* exponencial y *jitter*, respetando siempre `Retry-After`.

## 4. Códigos de error principales

| Código | Significado | Acción sugerida |
|--------|-------------|-----------------|
| 400 | Parámetros inválidos | Revisar el campo `error.param` de la respuesta |
| 401 | API key inválida o revocada | Verificar la clave y el entorno |
| 402 | Pago rechazado por el emisor | Mostrar `error.decline_code` al usuario de forma amigable |
| 409 | Conflicto de idempotencia | No reintentar con la misma clave y otro cuerpo |
| 429 | Límite de uso superado | Esperar `Retry-After` segundos |
| 5xx | Error interno de Andes Pay | Reintentar con backoff; consultar la página de estado |

## 5. Webhooks

Los webhooks notifican eventos de forma asíncrona (por ejemplo `payment.approved`, `refund.created`, `chargeback.created`).

### 5.1 Verificación de firma

Cada webhook incluye el encabezado `AndesPay-Signature`, que es un **HMAC-SHA256** del cuerpo crudo de la petición calculado con el *signing secret* del endpoint. El receptor debe recalcular la firma y compararla en tiempo constante. Además, el encabezado incluye un timestamp; se recomienda rechazar eventos con más de **5 minutos** de antigüedad para evitar ataques de repetición.

### 5.2 Reintentos

El endpoint del comercio debe responder con un código `2xx` en menos de **10 segundos**. Si no lo hace, Andes Pay reintenta el envío hasta **8 veces** a lo largo de **3 días**, con backoff exponencial. Después del último intento fallido, el evento queda marcado como "no entregado" y puede reenviarse manualmente desde el panel.

Los eventos pueden llegar **desordenados o duplicados**: el receptor debe ser idempotente usando el campo `event.id`.

## 6. Versionado

La versión de la API va en la URL (`/v2`). Los cambios que rompen compatibilidad solo se publican en una nueva versión mayor. Cuando sale una versión nueva, la anterior se mantiene durante **12 meses** antes de ser retirada.
