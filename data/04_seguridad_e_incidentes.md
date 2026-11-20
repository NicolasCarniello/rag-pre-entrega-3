# Andes Pay — Seguridad de la Información y Gestión de Incidentes

> Documento interno ficticio creado como dataset de ejemplo para el sistema RAG.
> Área: Seguridad. Clasificación: uso interno.

## 1. Principios

La plataforma de Andes Pay procesa datos de tarjetas y datos personales, por lo que la seguridad se basa en tres principios:

1. **Mínimo privilegio:** cada persona y cada servicio tiene solo los permisos que necesita.
2. **Defensa en profundidad:** ningún control es único; si uno falla, hay otro detrás.
3. **Trazabilidad:** toda acción sobre datos sensibles queda registrada.

## 2. Manejo de datos de tarjetas

- Los números de tarjeta (PAN) **nunca** se almacenan en los servidores del comercio. El frontend del comercio tokeniza la tarjeta con la clave pública y solo envía el token al backend.
- Andes Pay guarda los PAN cifrados con **AES-256** dentro de un entorno aislado certificado bajo PCI DSS. Las claves de cifrado se rotan cada **90 días** y se custodian en un módulo de seguridad de hardware (HSM).
- El código de seguridad (CVV) no se almacena nunca, ni siquiera cifrado.
- En los logs, los números de tarjeta se enmascaran mostrando solo los **primeros 6 y los últimos 4 dígitos**.

## 3. Accesos internos

- Todo el personal usa **autenticación multifactor (MFA)** con llave física para acceder a sistemas productivos. No se admite MFA por SMS.
- El acceso a bases de datos de producción es **temporal**: se solicita mediante un ticket, lo aprueba un líder técnico y expira automáticamente a las **4 horas**.
- Las cuentas de personas que dejan la empresa se desactivan el mismo día de la baja.
- Los permisos se revisan de forma trimestral.

## 4. Gestión de secretos en desarrollo

- Ninguna credencial (API keys, contraseñas, *signing secrets*) puede subirse al repositorio de código. Se usan variables de entorno y un gestor de secretos.
- El pipeline de integración continua ejecuta un escáner de secretos en cada *pull request*; si detecta una credencial, el merge se bloquea.
- Si una clave se expone por error, debe **rotarse de inmediato** aunque el commit se haya borrado, porque el historial de Git y los forks pueden conservarla.

## 5. Clasificación de incidentes

| Severidad | Descripción | Tiempo máximo de respuesta inicial |
|-----------|-------------|------------------------------------|
| SEV-1 | Caída total de cobros o filtración confirmada de datos | 15 minutos |
| SEV-2 | Degradación importante (por ejemplo, más del 5 % de errores en la API) | 1 hora |
| SEV-3 | Falla parcial sin impacto en cobros | 1 día hábil |
| SEV-4 | Problema menor o cosmético | Próximo sprint |

## 6. Proceso ante un incidente

1. **Detección:** por alertas automáticas, reportes de clientes o del equipo interno.
2. **Declaración:** la persona de guardia (*on-call*) declara el incidente y su severidad en el canal `#incidentes`.
3. **Roles:** en SEV-1 y SEV-2 se asignan un **Incident Commander**, que coordina; un responsable de comunicaciones, que actualiza la página de estado cada **30 minutos**; y los ingenieros que investigan.
4. **Mitigación:** la prioridad es restablecer el servicio, aunque no se conozca todavía la causa raíz (por ejemplo, hacer *rollback* del último despliegue).
5. **Cierre y postmortem:** dentro de los **5 días hábiles** posteriores a un SEV-1 o SEV-2 se publica un postmortem *blameless* (sin buscar culpables) con la línea de tiempo, la causa raíz y las acciones correctivas, cada una con un responsable y una fecha.

## 7. Notificación de filtraciones de datos

Si se confirma una filtración de datos personales, el equipo Legal debe notificar a la autoridad de protección de datos y a los afectados dentro de las **72 horas** desde la confirmación. La comunicación la redacta Legal junto con Seguridad; ningún otro equipo puede comunicar detalles del incidente de forma pública.

## 8. Programa de reporte de vulnerabilidades

Andes Pay tiene un programa de divulgación responsable. Los investigadores pueden reportar vulnerabilidades a `security@andespay.example`. El equipo de Seguridad confirma la recepción en **2 días hábiles** y se compromete a no iniciar acciones legales contra quien reporte de buena fe y respete las reglas del programa (no acceder a datos de terceros, no degradar el servicio y no divulgar la vulnerabilidad antes de que esté corregida).
