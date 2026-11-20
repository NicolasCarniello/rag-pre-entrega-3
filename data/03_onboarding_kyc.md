# Andes Pay — Onboarding de Comercios y Verificación de Identidad (KYC)

> Documento interno ficticio creado como dataset de ejemplo para el sistema RAG.
> Área: Compliance.

## 1. Para qué sirve el KYC

KYC (*Know Your Customer*) es el proceso por el cual Andes Pay verifica la identidad de cada comercio y de sus responsables antes de permitirle cobrar en producción. Es una obligación regulatoria de prevención de lavado de activos y también reduce el fraude: un comercio verificado tiene menos probabilidades de desaparecer después de cobrar.

Hasta completar el KYC, la cuenta solo puede operar en **sandbox**.

## 2. Tipos de cuenta

Andes Pay distingue dos tipos de comercio:

- **Persona humana:** profesionales independientes, monotributistas y emprendedores que facturan a su nombre.
- **Persona jurídica:** sociedades (SRL, SA, SAS) y otras entidades.

## 3. Documentación requerida

### 3.1 Persona humana

1. Documento de identidad vigente (frente y dorso).
2. Selfie con prueba de vida, tomada desde la app o desde la cámara web (no se aceptan fotos subidas desde la galería).
3. Constancia de inscripción fiscal.
4. Cuenta bancaria a nombre del titular para recibir las liquidaciones.

### 3.2 Persona jurídica

1. Estatuto o contrato social y sus modificaciones.
2. Constancia de inscripción fiscal de la sociedad.
3. Acta de designación de autoridades vigente.
4. Documento de identidad y prueba de vida del **representante legal**.
5. Identificación de los **beneficiarios finales**: toda persona humana que tenga, directa o indirectamente, **10 % o más** del capital o de los votos.
6. Cuenta bancaria a nombre de la sociedad.

## 4. Plazos de revisión

- **Revisión automática:** la mayoría de las cuentas de persona humana se aprueban en **menos de 10 minutos** si la validación biométrica y los datos fiscales coinciden.
- **Revisión manual:** si hay discrepancias, o si se trata de una persona jurídica, el equipo de Compliance revisa el caso en un plazo de **hasta 3 días hábiles**.
- Si falta documentación, la solicitud queda en estado `pending_documents`. Si el comercio no completa la información en **30 días**, la solicitud se cierra y hay que empezar de nuevo.

## 5. Niveles de cuenta y límites

| Nivel | Requisito | Límite mensual de cobro |
|-------|-----------|-------------------------|
| Nivel 1 | Email y teléfono verificados | Solo sandbox |
| Nivel 2 | KYC básico aprobado | Equivalente a USD 10.000 |
| Nivel 3 | KYC completo + justificación de ingresos | Sin límite fijo; sujeto a monitoreo de Riesgo |

Para pasar de nivel 2 a nivel 3 se debe presentar documentación que justifique el volumen esperado: últimas declaraciones impositivas, balances o extractos bancarios de los últimos 6 meses.

## 6. Rubros restringidos y prohibidos

**Prohibidos** (no se aprueban nunca): apuestas no autorizadas, venta de armas, criptoactivos sin registro ante el regulador, productos falsificados y esquemas piramidales.

**Restringidos** (requieren aprobación especial de Compliance): agencias de viaje, venta de bebidas alcohólicas, donaciones y organizaciones sin fines de lucro, y servicios de suscripción con prueba gratuita. Para estos rubros la revisión siempre es manual.

## 7. Revisión periódica

El KYC no es un trámite único. Andes Pay revisa los datos de cada comercio:

- **Cada 12 meses** para comercios de riesgo alto.
- **Cada 36 meses** para comercios de riesgo bajo o medio.

Además, el comercio debe informar en un plazo de **15 días** cualquier cambio de autoridades, de beneficiarios finales o de cuenta bancaria. Si no lo hace, la cuenta puede quedar con las liquidaciones suspendidas hasta regularizar.

## 8. Motivos frecuentes de rechazo

- La selfie no coincide con la foto del documento.
- El nombre del titular de la cuenta bancaria no coincide con el del comercio.
- El documento de identidad está vencido.
- La actividad declarada es un rubro prohibido.

Ante un rechazo, el comercio puede apelar **una sola vez** dentro de los 15 días, aportando documentación adicional.
