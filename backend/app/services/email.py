from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class EmailService(Protocol):
    def send_verification_email(self, to: str, token: str) -> None: ...
    def send_password_reset_email(self, to: str, token: str) -> None: ...
    def send_invitation_email(self, to: str, organization_name: str, token: str) -> None: ...


@dataclass
class SentEmail:
    to: str
    kind: str
    token: str
    organization_name: str | None = None


class ConsoleEmailService:
    # Development EmailService: captures emails in memory instead of sending
    # them. Deliberately never writes to the application logger -- sent_emails
    # is the only place a raw token ends up, and it's process-local, meant for
    # local development and test inspection, not a persistent/shipped log.
    def __init__(self) -> None:
        self.sent_emails: list[SentEmail] = []

    def send_verification_email(self, to: str, token: str) -> None:
        self.sent_emails.append(SentEmail(to=to, kind="verification", token=token))

    def send_password_reset_email(self, to: str, token: str) -> None:
        self.sent_emails.append(SentEmail(to=to, kind="password_reset", token=token))

    def send_invitation_email(self, to: str, organization_name: str, token: str) -> None:
        self.sent_emails.append(
            SentEmail(to=to, kind="invitation", token=token, organization_name=organization_name)
        )


_default_email_service: EmailService = ConsoleEmailService()


def get_email_service() -> EmailService:
    return _default_email_service
