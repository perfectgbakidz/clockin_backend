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
        # ✅ Must exactly match your frontend URL (protocol + domain + port if any)
        # Example for production:
        return os.environ.get("WEBAUTHN_ORIGIN", "https://clockin-pi.vercel.app")

    @staticmethod
    def _get_rp_id():
        # ✅ Must match the domain part of the frontend (no scheme)
        # For localhost testing: "localhost"
        # For prod: "clockin-pi.vercel.app"
        return os.environ.get("WEBAUTHN_RP_ID", "clockin-pi.vercel.app")

    @staticmethod
    def start_registration(user):
        """Generate registration options for a user."""
        existing_credentials = [
            PublicKeyCredentialDescriptor(
                type="public-key",
                id=cred.id,  # ✅ Make sure cred.id is stored as raw bytes (not hex/str)
                transports=[AuthenticatorTransport.TRANSPORT_USB],
            )
            for cred in user.webauthn_credentials
        ]

        options = generate_registration_options(
            rp_id=WebAuthnService._get_rp_id(),
            rp_name="Pardee Foods Attendance",
            user_id=str(user.id).encode(),  # ✅ Correct: backend library will base64url encode
            user_name=user.email,
            user_display_name=user.full_name or user.email,  # ✅ Add display name
            exclude_credentials=existing_credentials,
        )
        return options_to_json(options)  # ✅ Returns valid JSON with base64url-encoded challenge

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

        # ✅ Ensure credential ID is stored as raw bytes, not JSON string
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
                    id=cred.id,  # ✅ Must be raw bytes in DB
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
