-- MedSure schema (PostgreSQL). Generated from app/models.py. The app also creates these tables on startup.

CREATE TABLE otp_codes (
	id SERIAL NOT NULL, 
	phone VARCHAR(20) NOT NULL, 
	email VARCHAR(200) NOT NULL, 
	phone_hash VARCHAR(64) NOT NULL, 
	email_hash VARCHAR(64) NOT NULL, 
	expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	attempts INTEGER NOT NULL, 
	used BOOLEAN NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_otp_codes_phone ON otp_codes (phone);

CREATE TABLE users (
	id SERIAL NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	phone VARCHAR(20) NOT NULL, 
	email VARCHAR(200) NOT NULL, 
	role VARCHAR(10) NOT NULL, 
	language VARCHAR(8) NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_users_phone UNIQUE (phone)
);


CREATE TABLE cases (
	id SERIAL NOT NULL, 
	patient_id INTEGER NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (patient_id), 
	FOREIGN KEY(patient_id) REFERENCES users (id)
);


CREATE TABLE devices (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	fcm_token VARCHAR(500) NOT NULL, 
	platform VARCHAR(10) NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	UNIQUE (fcm_token)
);

CREATE INDEX ix_devices_user_id ON devices (user_id);

CREATE TABLE audit_events (
	id SERIAL NOT NULL, 
	case_id INTEGER NOT NULL, 
	alert_id VARCHAR(32), 
	actor VARCHAR(40) NOT NULL, 
	action VARCHAR(40) NOT NULL, 
	detail JSON NOT NULL, 
	at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id)
);

CREATE INDEX ix_audit_events_alert_id ON audit_events (alert_id);
CREATE INDEX ix_audit_events_case_id ON audit_events (case_id);

CREATE TABLE case_members (
	id SERIAL NOT NULL, 
	case_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	relation VARCHAR(20) NOT NULL, 
	permission VARCHAR(10) NOT NULL, 
	allow_alert_calls BOOLEAN NOT NULL, 
	priority INTEGER NOT NULL, 
	added_by INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_case_user UNIQUE (case_id, user_id), 
	FOREIGN KEY(case_id) REFERENCES cases (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(added_by) REFERENCES users (id)
);

CREATE INDEX ix_case_members_case_id ON case_members (case_id);

CREATE TABLE checkins (
	id SERIAL NOT NULL, 
	case_id INTEGER NOT NULL, 
	answers JSON NOT NULL, 
	note TEXT, 
	status VARCHAR(8) NOT NULL, 
	reasons JSON NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id)
);

CREATE INDEX ix_checkins_case_id ON checkins (case_id);

CREATE TABLE alerts (
	id VARCHAR(32) NOT NULL, 
	case_id INTEGER NOT NULL, 
	checkin_id INTEGER NOT NULL, 
	level VARCHAR(8) NOT NULL, 
	summary TEXT NOT NULL, 
	status VARCHAR(14) NOT NULL, 
	current_idx INTEGER NOT NULL, 
	next_run_at TIMESTAMP WITHOUT TIME ZONE, 
	dispatched_at TIMESTAMP WITHOUT TIME ZONE, 
	acknowledged_at TIMESTAMP WITHOUT TIME ZONE, 
	acknowledged_by INTEGER, 
	acknowledged_via VARCHAR(10), 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id), 
	FOREIGN KEY(checkin_id) REFERENCES checkins (id), 
	FOREIGN KEY(acknowledged_by) REFERENCES users (id)
);

CREATE INDEX ix_alerts_case_id ON alerts (case_id);
CREATE INDEX ix_alerts_due ON alerts (status, next_run_at);

CREATE TABLE alert_attempts (
	id SERIAL NOT NULL, 
	alert_id VARCHAR(32) NOT NULL, 
	user_id INTEGER NOT NULL, 
	channel VARCHAR(6) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	provider_ref VARCHAR(80), 
	detail TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(alert_id) REFERENCES alerts (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_alert_attempts_alert_id ON alert_attempts (alert_id);
CREATE INDEX ix_alert_attempts_provider_ref ON alert_attempts (provider_ref);
