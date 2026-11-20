# Andes Pay — Política de Reembolsos y Contracargos

> Documento interno ficticio creado como dataset de ejemplo para el sistema RAG.
> Versión 3.2 — Área de Operaciones.

## 1. Alcance

Esta política aplica a todos los cobros procesados por Andes Pay mediante tarjeta de crédito, tarjeta de débito, transferencia inmediata y saldo en cuenta. No aplica a los pagos en efectivo recibidos a través de la red de puntos de cobro físicos, que se rigen por el Anexo B de la política de cobranzas.

El objetivo es que los comercios que integran Andes Pay tengan reglas claras sobre cuándo pueden devolver dinero a un comprador, en qué plazos y con qué costos, y que el equipo de soporte responda siempre con el mismo criterio.

## 2. Plazos para solicitar un reembolso

- **Reembolso total:** el comercio puede devolver el 100 % de un cobro hasta **30 días corridos** después de la fecha de aprobación del pago.
- **Reembolso parcial:** se permiten hasta **5 reembolsos parciales** por cobro, siempre que la suma no supere el monto original y que se soliciten dentro de los mismos 30 días.
- **Pasados los 30 días:** el reembolso ya no puede hacerse desde el panel ni desde la API. El comercio debe abrir un ticket con el equipo de Operaciones, que evalúa el caso de forma manual en un plazo de hasta 5 días hábiles.

Los cobros con transferencia inmediata solo admiten reembolso total; no se pueden devolver de forma parcial.

## 3. Plazos de acreditación para el comprador

Una vez aprobado el reembolso, el dinero vuelve al comprador según el medio de pago original:

| Medio de pago original | Plazo de acreditación |
|------------------------|-----------------------|
| Saldo en cuenta Andes Pay | Inmediato |
| Transferencia inmediata | Hasta 24 horas hábiles |
| Tarjeta de débito | Entre 3 y 7 días hábiles |
| Tarjeta de crédito | Uno o dos resúmenes, según la fecha de cierre del emisor |

Andes Pay no controla los plazos de los bancos emisores. Si el comprador reclama, soporte debe enviarle el **número de operación de reembolso (ID RF)** para que lo presente ante su banco.

## 4. Costos de un reembolso

Cuando un comercio reembolsa un cobro, Andes Pay devuelve la comisión de procesamiento **solo si el reembolso es total y se realiza dentro de las primeras 72 horas** desde la aprobación del pago. En cualquier otro caso, la comisión original no se devuelve.

Los reembolsos parciales nunca generan devolución de comisión. No existe un cargo adicional por realizar un reembolso.

## 5. Contracargos (chargebacks)

Un contracargo ocurre cuando el titular de la tarjeta desconoce un consumo directamente ante su banco, sin pasar por el comercio.

### 5.1 Proceso

1. Andes Pay notifica al comercio por correo y por el webhook `chargeback.created`.
2. El monto en disputa se **retiene** del saldo disponible del comercio.
3. El comercio tiene **7 días corridos** para presentar documentación de respaldo (comprobante de entrega, conversación con el cliente, factura, registro de IP y dispositivo).
4. Andes Pay envía la documentación a la marca de la tarjeta. La resolución final puede tardar hasta 90 días.

### 5.2 Costo

Cada contracargo tiene un costo fijo de gestión de **USD 15**, que se cobra aunque el comercio gane la disputa. Si el comercio no presenta documentación en el plazo, el contracargo se da por perdido automáticamente.

### 5.3 Programa de monitoreo

Si un comercio supera un **1 % de contracargos** sobre el total de transacciones del mes durante dos meses consecutivos, ingresa al programa de monitoreo. Durante el monitoreo, los fondos se liberan con una demora adicional de 14 días y el equipo de Riesgo puede exigir medidas como validación 3-D Secure obligatoria.

## 6. Casos excluidos

No se permiten reembolsos sobre:

- Cobros que ya tienen un contracargo abierto (primero debe resolverse la disputa).
- Cobros de suscripciones canceladas hace más de 30 días.
- Cobros de cuentas suspendidas por el equipo de Riesgo; en ese caso, el reembolso lo gestiona directamente Operaciones.

## 7. Preguntas frecuentes de soporte

**¿El comprador puede pedir el reembolso directamente a Andes Pay?**
No. Andes Pay solo ejecuta reembolsos a pedido del comercio. Si un comprador escribe a soporte, se le indica que contacte al vendedor o, si no obtiene respuesta en 10 días, que abra un reclamo en el Centro de Disputas.

**¿Se puede reembolsar a una tarjeta distinta de la original?**
No. Por normas antilavado, el dinero siempre vuelve al medio de pago original.
