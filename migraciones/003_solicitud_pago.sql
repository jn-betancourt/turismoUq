-- Bitacora minima del canal de recepcion. Instalar una sola vez por esquema.
CREATE TABLE solicitud_pago (
    usuario_oracle VARCHAR2(128) NOT NULL,
    token_solicitud RAW(16) NOT NULL,
    id_pago NUMBER NOT NULL,
    CONSTRAINT pk_solicitud_pago PRIMARY KEY (usuario_oracle, token_solicitud),
    CONSTRAINT uq_solicitud_pago UNIQUE (id_pago),
    CONSTRAINT fk_solicitud_pago FOREIGN KEY (id_pago) REFERENCES pago (id_pago)
);

COMMENT ON TABLE solicitud_pago IS
    'Relaciona un token del usuario conectado con su comprobante, en la misma transaccion del pago.';
