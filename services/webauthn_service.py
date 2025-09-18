# services/webauthn_service.py
import os
from flask import current_app
from webauthn import (
    generate_registration_options,
    options_to_json,
    verify_registration_response,
    generate_authentication_options,
    verify_authentication_response,
)
from webauthn.helpers.structs import (
    PublicKeyCredentialDescriptor,
    RegistrationCredential,
    AuthenticationCredential,
    AuthenticatorTransport,
)
from models import WebAuthnCredential
from database import db


class WebAuthnService:
    @staticmethod
    def _get_origin():
        return os.environ.get("WEBAUTHN_ORIGIN", "http://localhost:3000")

    @staticmethod
    def _get_rp_id():
        return os.environ.get("WEBAUTHN_RP_ID", "localhost")

    @staticmethod
    def start_registration(user):
        """Generate registration options for a user."""
        existing_credentials = [
            PublicKeyCredentialDescriptor(
                type="public-key",
                id=cred.id,
                transports=[AuthenticatorTransport.TRANSPORT_USB],
            )
            for cred in user.webauthn_credentials
        ]

        options = generate_registration_options(
            rp_id=WebAuthnService._get_rp_id(),
            rp_name="Pardee Foods Attendance",
            user_id=str(user.id).encode(),
            user_name=user.email,
            exclude_credentials=existing_credentials,
        )
        return options_to_json(options)

    @staticmethod
    def finish_registration(user, response_json, expected_challenge: str):
        """Verify registration response and store credential."""
        credential = RegistrationCredential.parse_raw(response_json)

        verification = verify_registration_response(
            credential=credential,
            expected_challenge=expected_challenge,
            expected_origin=WebAuthnService._get_origin(),
            expected_rp_id=WebAuthnService._get_rp_id(),
        )

        # Store credential in DB
        cred = WebAuthnCredential(
            id=verification.credential_id,
            user_id=user.id,
            public_key=verification.credential_public_key,
            counter=verification.sign_count,
            transports=[t.value for t in credential.response.transports] if credential.response.transports else [],
        )
        db.session.add(cred)
        db.session.commit()
        return cred

    @staticmethod
    def start_authentication(user):
        """Generate authentication options."""
        options = generate_authentication_options(
            rp_id=WebAuthnService._get_rp_id(),
            allow_credentials=[
                PublicKeyCredentialDescriptor(
                    type="public-key",
                    id=cred.id,
                    transports=[AuthenticatorTransport.TRANSPORT_USB],
                )
                for cred in user.webauthn_credentials
            ],
        )
        return options_to_json(options)

    @staticmethod
    def finish_authentication(user, response_json, expected_challenge: str):
        """Verify authentication response."""
        credential = AuthenticationCredential.parse_raw(response_json)

        db_cred = WebAuthnCredential.query.filter_by(
            id=credential.raw_id, user_id=user.id
        ).first()
        if not db_cred:
            raise ValueError("Credential not found")

        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=expected_challenge,
            expected_rp_id=WebAuthnService._get_rp_id(),
            expected_origin=WebAuthnService._get_origin(),
            credential_public_key=db_cred.public_key,
            credential_current_sign_count=db_cred.counter,
        )

        db_cred.counter = verification.new_sign_count
        db.session.commit()
        return verification
