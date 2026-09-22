from datetime import datetime, timedelta, timezone
import secrets
import re
import ipaddress
import dns.resolver

import httpx
from fastapi import Depends, FastAPI, HTTPException, Header, Request
from fastapi.responses import FileResponse
from jose import JWTError, jwt
import bcrypt
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models.models import (
    Activity,
    AnalyticsDaily,
    Domain,
    DomainStatus,
    GuestSession,
    Mailbox,
    MailboxType,
    User,
    UserRole,
)


def normalize_domain(domain: str) -> str:
    domain = str(domain or "").strip().lower()
    domain = domain.rstrip(".")
    return domain


class CreateUserMailboxRequest(BaseModel):
    domain: str
    username: str | None = None


app = FastAPI(
    title="TempMail Application API",
    description="Application layer for the TempMail website",
    version="1.0.0",
)


@app.get("/", include_in_schema=False)
def frontend():
    return FileResponse("/app/frontend/index.html")


@app.get("/styles.css", include_in_schema=False)
def frontend_styles():
    return FileResponse(
        "/app/frontend/styles.css",
        media_type="text/css",
    )


@app.get("/app.js", include_in_schema=False)
def frontend_script():
    return FileResponse(
        "/app/frontend/app.js",
        media_type="application/javascript",
    )


JWT_ALGORITHM = "HS256"

def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")

    if len(password_bytes) > 72:
        raise HTTPException(
            status_code=400,
            detail="Password must not exceed 72 bytes.",
        )

    return bcrypt.hashpw(
        password_bytes,
        bcrypt.gensalt(),
    ).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    password_bytes = password.encode("utf-8")

    if len(password_bytes) > 72:
        return False

    try:
        return bcrypt.checkpw(
            password_bytes,
            password_hash.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: int) -> str:
    now = utcnow()

    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(
            minutes=settings.jwt_expire_minutes
        ),
    }

    return jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=JWT_ALGORITHM,
    )


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Authorization header required.",
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization header.",
        )

    token = authorization[7:].strip()

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[JWT_ALGORITHM],
        )

        user_id = payload.get("sub")

        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="Invalid access token.",
            )

        user = (
            db.query(User)
            .filter(User.id == int(user_id))
            .first()
        )

    except (JWTError, ValueError):
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired access token.",
        )

    if not user or not user.is_active:
        raise HTTPException(
            status_code=401,
            detail="User account is inactive or does not exist.",
        )

    return user

def get_current_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=403,
            detail="Administrator access required.",
        )

    return current_user
    
    
# ---------------------------------------------------------
# Schemas
# ---------------------------------------------------------

class GuestSessionResponse(BaseModel):
    session_token: str
    expires_at: datetime
    country: str
    country_code: str


class CreateMailboxRequest(BaseModel):
    username: str | None = None
    domain: str | None = None


class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str
    user: dict
    
class CreateAdminMailboxRequest(BaseModel):
    domain: str | None = None
    username: str | None = None
    
class CreateDomainRequest(BaseModel):
    domain: str
    
    

# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_verified_domain(
    db: Session,
    requested_domain: str | None,
) -> Domain:
    if requested_domain:
        domain = (
            db.query(Domain)
            .filter(
                Domain.domain == requested_domain.lower(),
                Domain.status == DomainStatus.VERIFIED,
            )
            .first()
        )
    else:
        domain = (
            db.query(Domain)
            .filter(Domain.status == DomainStatus.VERIFIED)
            .order_by(Domain.id.asc())
            .first()
        )

    if not domain:
        raise HTTPException(
            status_code=400,
            detail="No verified domain is available.",
        )

    return domain
    

COUNTRY_CACHE = {}


async def get_client_country(request: Request) -> tuple[str, str]:
    client_ip = request.headers.get("X-Real-IP")

    if not client_ip:
        forwarded_for = request.headers.get("X-Forwarded-For", "")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()

    if not client_ip and request.client:
        client_ip = request.client.host

    if not client_ip:
        return "Unknown", "XX"

    try:
        ip_obj = ipaddress.ip_address(client_ip)

        if (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_reserved
        ):
            return "Unknown", "XX"

    except ValueError:
        return "Unknown", "XX"

    if client_ip in COUNTRY_CACHE:
        return COUNTRY_CACHE[client_ip]

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(
                "https://api.ip2location.io/",
                params={
                    "ip": client_ip,
                    "format": "json",
                },
            )

        if response.status_code == 200:
            data = response.json()

            country_code = (
                data.get("country_code")
                or "XX"
            ).upper()

            country_name = (
                data.get("country_name")
                or "Unknown"
            )

            result = (country_name, country_code)

            COUNTRY_CACHE[client_ip] = result

            return result

    except Exception as exc:
        print(
            f"IP geolocation lookup failed for "
            f"{client_ip}: {exc}"
        )

    return "Unknown", "XX"


def get_dns_records(domain: str, verification_token: str | None = None) -> dict:
    return {
        "verification": {
            "type": "TXT",
            "name": f"_tempmail-verification.{domain}",
            "value": verification_token,
        },
        "mx": {
            "type": "MX",
            "name": "@",
            "value": f"mail.{domain}",
            "priority": 10,
        },
        "mail_a": {
            "type": "A",
            "name": f"mail.{domain}",
            "value": "2.25.196.198",
        },
    }


def get_authoritative_nameservers(domain: str) -> list[str]:
    try:
        answers = dns.resolver.resolve(
            domain,
            "NS",
            lifetime=5,
        )

        return [
            str(answer.target).rstrip(".")
            for answer in answers
        ]

    except (
        dns.resolver.NXDOMAIN,
        dns.resolver.NoAnswer,
        dns.resolver.NoNameservers,
        dns.exception.Timeout,
    ):
        return []


def get_nameserver_ips(nameserver: str) -> list[str]:
    ips = []

    for record_type in ("A", "AAAA"):
        try:
            answers = dns.resolver.resolve(
                nameserver,
                record_type,
                lifetime=5,
            )

            ips.extend(
                str(answer)
                for answer in answers
            )

        except (
            dns.resolver.NXDOMAIN,
            dns.resolver.NoAnswer,
            dns.resolver.NoNameservers,
            dns.exception.Timeout,
        ):
            continue

    return ips


def resolve_txt(
    name: str,
    domain: str,
) -> list[str]:
    nameservers = get_authoritative_nameservers(domain)

    values = []

    for nameserver in nameservers:
        nameserver_ips = get_nameserver_ips(nameserver)

        for nameserver_ip in nameserver_ips:
            resolver = dns.resolver.Resolver(
                configure=False
            )

            resolver.nameservers = [
                nameserver_ip
            ]

            resolver.timeout = 3
            resolver.lifetime = 5

            try:
                answers = resolver.resolve(
                    name,
                    "TXT",
                )

                for answer in answers:
                    parts = getattr(
                        answer,
                        "strings",
                        None,
                    )

                    if parts:
                        value = b"".join(
                            parts
                        ).decode(
                            "utf-8",
                            errors="replace",
                        )
                    else:
                        value = str(
                            answer
                        ).strip('"')

                    values.append(
                        value.strip()
                    )

            except (
                dns.resolver.NXDOMAIN,
                dns.resolver.NoAnswer,
                dns.resolver.NoNameservers,
                dns.exception.Timeout,
            ):
                continue

    return list(dict.fromkeys(values))


def resolve_mx(domain: str) -> list[tuple[str, int]]:
    try:
        answers = dns.resolver.resolve(
            domain,
            "MX",
            lifetime=5,
        )

        return [
            (
                str(answer.exchange).rstrip(".").lower(),
                int(answer.preference),
            )
            for answer in answers
        ]

    except (
        dns.resolver.NXDOMAIN,
        dns.resolver.NoAnswer,
        dns.resolver.NoNameservers,
        dns.exception.Timeout,
    ):
        return []


def resolve_a(hostname: str) -> list[str]:
    try:
        answers = dns.resolver.resolve(
            hostname,
            "A",
            lifetime=5,
        )

        return [
            str(answer)
            for answer in answers
        ]

    except (
        dns.resolver.NXDOMAIN,
        dns.resolver.NoAnswer,
        dns.resolver.NoNameservers,
        dns.exception.Timeout,
    ):
        return []
        
        
async def create_upstream_mailbox(
    username: str | None,
    domain: str,
) -> dict:
    payload = {}

    if username:
        payload["username"] = username

    if domain:
        payload["domain"] = domain

    url = f"{settings.tempmail_api}/api/v1/addresses"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload)

        if response.status_code >= 400:
            try:
                detail = response.json()
            except Exception:
                detail = response.text

            raise HTTPException(
                status_code=response.status_code,
                detail=detail,
            )

        return response.json()

    except HTTPException:
        raise

    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Tempmail server unavailable: {exc}",
        )


def increment_daily_generated(db: Session) -> None:
    today = utcnow().date()

    row = (
        db.query(AnalyticsDaily)
        .filter(AnalyticsDaily.date == today)
        .first()
    )

    if not row:
        row = AnalyticsDaily(
            date=today,
            registered_users=0,
            emails_generated=0,
            emails_received=0,
        )
        db.add(row)

    row.emails_generated += 1


def increment_daily_received(db: Session) -> None:
    today = utcnow().date()

    row = (
        db.query(AnalyticsDaily)
        .filter(AnalyticsDaily.date == today)
        .first()
    )

    if not row:
        row = AnalyticsDaily(
            date=today,
            registered_users=0,
            emails_generated=0,
            emails_received=0,
        )
        db.add(row)

    row.emails_received += 1


# ---------------------------------------------------------
# Basic endpoints
# ---------------------------------------------------------


@app.get("/health")
async def health():
    return {
        "status": "ok",
    }

@app.get("/api/auth/me")
async def me(
    current_user: User = Depends(get_current_user),
):
    return {
    "id": current_user.id,
    "username": current_user.username,
    "email": current_user.email,
    "country": current_user.country,
    "country_code": current_user.country_code,
    "role": current_user.role,
    }
    
@app.get("/api/user/mailboxes")
def get_user_mailboxes(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mailboxes = (
        db.query(Mailbox)
        .filter(
            Mailbox.user_id == current_user.id,
            Mailbox.mailbox_type == MailboxType.USER.value,
            Mailbox.is_active.is_(True),
        )
        .order_by(Mailbox.created_at.desc())
        .all()
    )

    return {
        "mailboxes": [
            {
                "id": mailbox.id,
                "email": mailbox.email,
                "country": mailbox.country,
"country_code": mailbox.country_code,
"mailbox_type": mailbox.mailbox_type,
                "expires_at": mailbox.expires_at,
                "is_active": mailbox.is_active,
                "created_at": mailbox.created_at,
            }
            for mailbox in mailboxes
        ],
        "total": len(mailboxes),
    }
    
@app.get("/api/user/mailbox/{mailbox_id}/emails")
async def get_user_mailbox_emails(
    mailbox_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mailbox = (
        db.query(Mailbox)
        .filter(
            Mailbox.id == mailbox_id,
            Mailbox.user_id == current_user.id,
            Mailbox.mailbox_type == MailboxType.USER.value,
            Mailbox.is_active.is_(True),
        )
        .first()
    )

    if not mailbox:
        raise HTTPException(
            status_code=404,
            detail="Mailbox not found.",
        )

    try:
        async with httpx.AsyncClient(
            timeout=15.0
        ) as client:
            response = await client.get(
                f"{settings.tempmail_api}/api/v1/{mailbox.tempmail_token}/emails"
            )

    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail="Unable to connect to the mail server.",
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail="Mail server returned an error.",
        )

    data = response.json()
    emails = data.get("emails", [])

    new_count = 0

    for email in emails:
        message_id = email.get("id")

        if not message_id:
            continue

        existing = (
            db.query(Activity)
            .filter(
                Activity.event == "email_received",
                Activity.user_id == current_user.id,
            )
            .all()
        )

        already_recorded = any(
            activity.metadata_json
            and activity.metadata_json.get("mailbox_id") == mailbox.id
            and activity.metadata_json.get("message_id") == message_id
            for activity in existing
        )

        if already_recorded:
            continue

        db.add(
            Activity(
                user_id=current_user.id,
                event="email_received",
                country=mailbox.country,
                created_at=utcnow(),
                metadata_json={
                    "mailbox_id": mailbox.id,
                    "message_id": message_id,
                    "domain": mailbox.domain.domain,
                    "received_at": email.get("received_at"),
                },
            )
        )

        increment_daily_received(db)
        new_count += 1

    if new_count:
        db.commit()

    return data


@app.get("/api/user/mailbox/{mailbox_id}/emails/{email_id}")
async def get_user_mailbox_email(
    mailbox_id: int,
    email_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mailbox = (
        db.query(Mailbox)
        .filter(
            Mailbox.id == mailbox_id,
            Mailbox.user_id == current_user.id,
            Mailbox.mailbox_type == MailboxType.USER.value,
            Mailbox.is_active.is_(True),
        )
        .first()
    )

    if not mailbox:
        raise HTTPException(
            status_code=404,
            detail="Mailbox not found.",
        )

    email_id = str(email_id).strip()

    if not email_id or len(email_id) > 200:
        raise HTTPException(
            status_code=400,
            detail="Invalid email ID.",
        )

    url = (
        f"{settings.tempmail_api.rstrip('/')}"
        f"/api/v1/{mailbox.tempmail_token}/emails/{email_id}"
    )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url)

    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail="Unable to connect to the mail server.",
        )

    if response.status_code == 404:
        raise HTTPException(
            status_code=404,
            detail="Email message not found.",
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail="Mail server returned an error.",
        )

    try:
        return response.json()
    except ValueError:
        raise HTTPException(
            status_code=502,
            detail="Mail server returned invalid JSON.",
        )


# ---------------------------------------------------------
# Domains
# ---------------------------------------------------------

@app.get("/api/domains")
async def domains(db: Session = Depends(get_db)):
    rows = (
        db.query(Domain)
        .filter(Domain.status == DomainStatus.VERIFIED)
        .order_by(Domain.domain.asc())
        .all()
    )

    return {
        "domains": [row.domain for row in rows],
    }
    
    
async def provision_upstream_domain(domain: str) -> dict:
    headers = {
        "Authorization": f"Bearer {settings.provisioner_token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=130.0) as client:
            response = await client.post(
                f"{settings.provisioner_url.rstrip('/')}/provision",
                json={"domain": domain},
                headers=headers,
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Domain provisioner unavailable: {exc}",
        )

    if response.status_code != 200:
        try:
            detail = response.json().get("detail", "Provisioning failed.")
        except Exception:
            detail = response.text or "Provisioning failed."

        raise HTTPException(
            status_code=502,
            detail=detail,
        )

    return response.json()


@app.get("/api/admin/me")
def admin_me(
    current_admin: User = Depends(get_current_admin),
):
    return {
        "id": current_admin.id,
        "username": current_admin.username,
        "email": current_admin.email,
        "country": current_admin.country,
        "role": current_admin.role,
        "is_active": current_admin.is_active,
        "created_at": current_admin.created_at,
    }
    
    
@app.get("/api/admin/dashboard")
def admin_dashboard(
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    total_users = (
        db.query(User)
        .filter(User.role == UserRole.USER.value)
        .count()
    )

    total_admins = (
        db.query(User)
        .filter(User.role == UserRole.ADMIN.value)
        .count()
    )

    total_guests = db.query(GuestSession).count()

    total_mailboxes = db.query(Mailbox).count()

    active_mailboxes = (
        db.query(Mailbox)
        .filter(Mailbox.is_active.is_(True))
        .count()
    )

    total_domains = db.query(Domain).count()

    verified_domains = (
        db.query(Domain)
        .filter(
            Domain.status == DomainStatus.VERIFIED.value
        )
        .count()
    )

    pending_domains = (
        db.query(Domain)
        .filter(
            Domain.status == DomainStatus.PENDING.value
        )
        .count()
    )

    total_activities = db.query(Activity).count()

    return {
        "users": {
            "registered": total_users,
            "admins": total_admins,
            "guests": total_guests,
        },
        "mailboxes": {
            "total": total_mailboxes,
            "active": active_mailboxes,
        },
        "domains": {
            "total": total_domains,
            "verified": verified_domains,
            "pending": pending_domains,
        },
        "activity": {
            "total": total_activities,
        },
    }
    
@app.get("/api/admin/mailboxes")
def admin_mailboxes(
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Mailbox)
        .order_by(Mailbox.created_at.desc())
        .all()
    )

    return {
        "mailboxes": [
            {
                "id": mailbox.id,
                "email": mailbox.email,
                "mailbox_type": mailbox.mailbox_type,
                "user_id": mailbox.user_id,
                "guest_session_id": mailbox.guest_session_id,
                "domain": mailbox.domain.domain,
                "country": mailbox.country,
                "created_at": mailbox.created_at,
                "expires_at": mailbox.expires_at,
                "is_active": mailbox.is_active,
            }
            for mailbox in rows
        ],
        "total": len(rows),
    }
    
@app.get("/api/admin/users")
def admin_users(
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    users = (
        db.query(User)
        .order_by(User.created_at.desc())
        .all()
    )

    return {
        "users": [
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "country": user.country,
                "role": user.role,
                "is_active": user.is_active,
                "created_at": user.created_at,
            }
            for user in users
        ],
        "total": len(users),
    }
    
    
@app.get("/api/admin/activity")
def admin_activity(
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    activities = (
        db.query(Activity)
        .order_by(Activity.created_at.desc())
        .limit(100)
        .all()
    )

    return {
        "activities": [
            {
                "id": activity.id,
                "user_id": activity.user_id,
                "guest_session_id": activity.guest_session_id,
                "event": activity.event,
                "country": activity.country,
                "created_at": activity.created_at,
                "metadata": activity.metadata_json,
            }
            for activity in activities
        ],
        "total": len(activities),
    }
    
    
@app.get("/api/admin/analytics")
def admin_analytics(
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(AnalyticsDaily)
        .order_by(AnalyticsDaily.date.desc())
        .limit(30)
        .all()
    )

    return {
        "analytics": [
            {
                "date": row.date,
                "registered_users": row.registered_users,
                "emails_generated": row.emails_generated,
                "emails_received": row.emails_received,
            }
            for row in reversed(rows)
        ]
    }
    
@app.get("/api/admin/domains")
def list_admin_domains(
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    domains = (
        db.query(Domain)
        .order_by(Domain.created_at.desc())
        .all()
    )

    result = []

    for domain in domains:
        item = {
            "id": domain.id,
            "domain": domain.domain,
            "status": domain.status,
            "verified_at": domain.verified_at,
            "created_at": domain.created_at,
        }

        # Verification details are only needed while a domain
        # is pending. Never expose the verification token after
        # verification or disablement.
        if domain.status == DomainStatus.PENDING.value:
            item["verification_token"] = domain.verification_token
            item["dns"] = get_dns_records(
                domain.domain,
                domain.verification_token,
            )
        else:
            item["verification_token"] = None
            item["dns"] = get_dns_records(
                domain.domain,
                None,
            )

        result.append(item)

    return {
        "domains": result,
        "total": len(result),
    }


# ---------------------------------------------------------
# Guest sessions
# ---------------------------------------------------------

@app.post(
    "/api/guest/session",
    response_model=GuestSessionResponse,
)
async def create_guest_session(
    request: Request,
    db: Session = Depends(get_db),
):
    now = utcnow()

    country, country_code = await get_client_country(request)

    session_token = secrets.token_urlsafe(32)

    expires_at = now + timedelta(minutes=20)

    guest = GuestSession(
        session_token=session_token,
        country=country,
        country_code=country_code,
        created_at=now,
        expires_at=expires_at,
    )

    db.add(guest)
    db.flush()

    db.add(
        Activity(
            guest_session_id=guest.id,
            event="guest_session_created",
            country=country,
            country_code=country_code,
            created_at=now,
        )
    )

    db.commit()

    return GuestSessionResponse(
        session_token=session_token,
        expires_at=expires_at,
        country=country,
        country_code=country_code,
    )


# ---------------------------------------------------------
# Guest mailbox creation
# ---------------------------------------------------------

@app.post("/api/guest/mailbox")
async def create_guest_mailbox(
    data: CreateMailboxRequest,
    session_token: str,
    db: Session = Depends(get_db),
):
    now = utcnow()

    guest = (
        db.query(GuestSession)
        .filter(GuestSession.session_token == session_token)
        .first()
    )

    if not guest:
        raise HTTPException(
            status_code=401,
            detail="Invalid guest session.",
        )

    if guest.expires_at <= now:
        raise HTTPException(
            status_code=410,
            detail="Guest session has expired.",
        )

    domain = get_verified_domain(db, data.domain)

    upstream = await create_upstream_mailbox(
        username=data.username,
        domain=domain.domain,
    )

    email_address = upstream.get("email")
    upstream_token = upstream.get("token")

    if not email_address or not upstream_token:
        raise HTTPException(
            status_code=502,
            detail="Tempmail server returned an invalid mailbox.",
        )

    mailbox = Mailbox(
        email=email_address,
        tempmail_token=upstream_token,
        mailbox_type=MailboxType.GUEST.value,
        user_id=None,
        guest_session_id=guest.id,
        domain_id=domain.id,
        country=guest.country,
        country_code=guest.country_code,
        created_at=now,
        expires_at=guest.expires_at,
        is_active=True,
    )

    db.add(mailbox)
    db.flush()

    db.add(
        Activity(
            guest_session_id=guest.id,
            event="guest_mailbox_created",
            country=guest.country,
            country_code=guest.country_code,
            created_at=now,
            metadata_json={
                "domain": domain.domain,
                "mailbox_type": "guest",
            },
        )
    )

    increment_daily_generated(db)

    db.commit()
    db.refresh(mailbox)

    return {
        "id": mailbox.id,
        "email": mailbox.email,
        "expires_at": mailbox.expires_at,
        "mailbox_type": mailbox.mailbox_type,
        "country": mailbox.country,
        "country_code": mailbox.country_code,
    }


@app.get("/api/guest/mailbox/{mailbox_id}/emails")
async def get_guest_emails(
    mailbox_id: int,
    session_token: str,
    db: Session = Depends(get_db),
):
    now = utcnow()

    guest = (
        db.query(GuestSession)
        .filter(GuestSession.session_token == session_token)
        .first()
    )

    if not guest:
        raise HTTPException(
            status_code=401,
            detail="Invalid guest session.",
        )

    if guest.expires_at <= now:
        raise HTTPException(
            status_code=410,
            detail="Guest session has expired.",
        )

    mailbox = (
        db.query(Mailbox)
        .filter(
            Mailbox.id == mailbox_id,
            Mailbox.guest_session_id == guest.id,
            Mailbox.mailbox_type == MailboxType.GUEST.value,
            Mailbox.is_active.is_(True),
        )
        .first()
    )

    if not mailbox:
        raise HTTPException(
            status_code=404,
            detail="Mailbox not found.",
        )

    if mailbox.expires_at and mailbox.expires_at <= now:
        mailbox.is_active = False
        db.commit()

        raise HTTPException(
            status_code=410,
            detail="Mailbox has expired.",
        )

    url = (
        f"{settings.tempmail_api}"
        f"/api/v1/{mailbox.tempmail_token}/emails"
    )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url)

    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail="Unable to connect to the mail server.",
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail="Mail server returned an error.",
        )

    data = response.json()
    emails = data.get("emails", [])

    new_count = 0

    for email in emails:
        message_id = email.get("id")

        if not message_id:
            continue

        existing = (
            db.query(Activity)
            .filter(
                Activity.event == "email_received",
                Activity.guest_session_id == guest.id,
            )
            .all()
        )

        already_recorded = any(
            activity.metadata_json
            and activity.metadata_json.get("mailbox_id") == mailbox.id
            and activity.metadata_json.get("message_id") == message_id
            for activity in existing
        )

        if already_recorded:
            continue

        db.add(
            Activity(
                guest_session_id=guest.id,
                event="email_received",
                country=mailbox.country,
                created_at=now,
                metadata_json={
                    "mailbox_id": mailbox.id,
                    "message_id": message_id,
                    "domain": mailbox.domain.domain,
                    "received_at": email.get("received_at"),
                },
            )
        )

        increment_daily_received(db)
        new_count += 1

    if new_count:
        db.commit()

    return data


@app.get("/api/guest/mailbox/{mailbox_id}/emails/{email_id}")
async def get_guest_mailbox_email(
    mailbox_id: int,
    email_id: str,
    session_token: str,
    db: Session = Depends(get_db),
):
    now = utcnow()

    guest = (
        db.query(GuestSession)
        .filter(GuestSession.session_token == session_token)
        .first()
    )

    if not guest:
        raise HTTPException(
            status_code=401,
            detail="Invalid guest session.",
        )

    if guest.expires_at <= now:
        raise HTTPException(
            status_code=410,
            detail="Guest session has expired.",
        )

    mailbox = (
        db.query(Mailbox)
        .filter(
            Mailbox.id == mailbox_id,
            Mailbox.guest_session_id == guest.id,
            Mailbox.mailbox_type == MailboxType.GUEST.value,
            Mailbox.is_active.is_(True),
        )
        .first()
    )

    if not mailbox:
        raise HTTPException(
            status_code=404,
            detail="Mailbox not found.",
        )

    if mailbox.expires_at and mailbox.expires_at <= now:
        mailbox.is_active = False
        db.commit()
        raise HTTPException(
            status_code=410,
            detail="Mailbox has expired.",
        )

    email_id = str(email_id).strip()

    if not email_id or len(email_id) > 200:
        raise HTTPException(
            status_code=400,
            detail="Invalid email ID.",
        )

    url = (
        f"{settings.tempmail_api.rstrip('/')}"
        f"/api/v1/{mailbox.tempmail_token}/emails/{email_id}"
    )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url)

    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail="Unable to connect to the mail server.",
        )

    if response.status_code == 404:
        raise HTTPException(
            status_code=404,
            detail="Email message not found.",
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail="Mail server returned an error.",
        )

    try:
        return response.json()
    except ValueError:
        raise HTTPException(
            status_code=502,
            detail="Mail server returned invalid JSON.",
        )


@app.post("/api/auth/register", response_model=AuthResponse)
async def register(
    request: Request,
    data: RegisterRequest,
    db: Session = Depends(get_db),
):
    username = data.username.strip()
    email = str(data.email).lower().strip()

    if len(username) < 3:
        raise HTTPException(
            status_code=400,
            detail="Username must contain at least 3 characters.",
        )

    if len(data.password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must contain at least 8 characters.",
        )

    existing_username = (
        db.query(User)
        .filter(User.username == username)
        .first()
    )

    if existing_username:
        raise HTTPException(
            status_code=409,
            detail="Username already exists.",
        )

    existing_email = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    if existing_email:
        raise HTTPException(
            status_code=409,
            detail="Email already exists.",
        )

    now = utcnow()

    country, country_code = await get_client_country(request)

    user = User(
        username=username,
        email=email,
        password_hash=hash_password(data.password),
        country=country,
        country_code=country_code,
        role=UserRole.USER.value,
        is_active=True,
        created_at=now,
    )

    db.add(user)
    db.flush()

    db.add(
        Activity(
            user_id=user.id,
            event="user_registered",
            country=country,
            country_code=country_code,
            created_at=now,
        )
    )

    analytics = (
        db.query(AnalyticsDaily)
        .filter(AnalyticsDaily.date == now.date())
        .first()
    )

    if not analytics:
        analytics = AnalyticsDaily(
            date=now.date(),
            registered_users=1,
            emails_generated=0,
            emails_received=0,
        )
        db.add(analytics)
    else:
        analytics.registered_users += 1

    db.commit()
    db.refresh(user)

    access_token = create_access_token(
        {
            "sub": str(user.id),
            "role": user.role,
        }
    )

    return AuthResponse(
        access_token=access_token,
        token_type="bearer",
        user={
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "country": user.country,
            "country_code": user.country_code,
            "role": user.role,
        },
    )

@app.post("/api/auth/login", response_model=AuthResponse)
async def login(
    data: LoginRequest,
    db: Session = Depends(get_db),
):
    email = str(data.email).lower().strip()

    user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    if not user or not verify_password(
        data.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Account is disabled.",
        )

    access_token = create_access_token(user.id)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "country": user.country,
            "role": user.role,
        },
    }
    
@app.post("/api/user/mailbox")
async def create_user_mailbox(
    request: Request,
    data: CreateUserMailboxRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    domain = data.domain.strip().lower()

    if not domain:
        raise HTTPException(
            status_code=400,
            detail="Domain is required.",
        )

    verified_domain = (
        db.query(Domain)
        .filter(
            Domain.domain == domain,
            Domain.status == DomainStatus.VERIFIED.value,
        )
        .first()
    )

    if not verified_domain:
        raise HTTPException(
            status_code=404,
            detail="Verified domain not found.",
        )

    country, country_code = await get_client_country(request)

    if data.username:
        username = data.username.strip().lower()

        if len(username) < 3 or len(username) > 64:
            raise HTTPException(
                status_code=400,
                detail="Mailbox username must be between 3 and 64 characters.",
            )

        if not re.fullmatch(
            r"[a-z0-9](?:[a-z0-9._-]{1,62}[a-z0-9])?",
            username,
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid mailbox username. "
                    "Use only lowercase letters, numbers, dots, "
                    "underscores, and hyphens."
                ),
            )
    else:
        username = secrets.token_hex(5)

    upstream = await create_upstream_mailbox(
        username=username,
        domain=domain,
    )

    email_address = upstream["email"]
    upstream_token = upstream["token"]

    mailbox = Mailbox(
        email=email_address,
        tempmail_token=upstream_token,
        mailbox_type=MailboxType.USER.value,
        user_id=current_user.id,
        guest_session_id=None,
        domain_id=verified_domain.id,
        country=country,
        country_code=country_code,
        expires_at=None,
        is_active=True,
    )

    db.add(mailbox)
    db.flush()

    db.add(
        Activity(
            user_id=current_user.id,
            event="user_mailbox_created",
            country=country,
            country_code=country_code,
            created_at=utcnow(),
            metadata_json={
                "mailbox_id": mailbox.id,
                "domain": domain,
                "username": username,
            },
        )
    )

    today = utcnow().date()

    analytics = (
        db.query(AnalyticsDaily)
        .filter(AnalyticsDaily.date == today)
        .first()
    )

    if not analytics:
        analytics = AnalyticsDaily(
            date=today,
            registered_users=0,
            emails_generated=1,
            emails_received=0,
        )
        db.add(analytics)
    else:
        analytics.emails_generated += 1

    db.commit()
    db.refresh(mailbox)

    return {
        "id": mailbox.id,
        "email": mailbox.email,
        "domain": verified_domain.domain,
        "country": mailbox.country,
        "country_code": mailbox.country_code,
        "mailbox_type": mailbox.mailbox_type,
        "expires_at": None,
        "is_active": mailbox.is_active,
    }


@app.post("/api/admin/mailbox")
async def create_admin_mailbox(
    request: Request,
    data: CreateAdminMailboxRequest,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):

    country, country_code = await get_client_country(request)
    domain = get_verified_domain(db, data.domain)

    username = None

    if data.username:
        username = data.username.strip().lower()

        if len(username) < 3 or len(username) > 64:
            raise HTTPException(
                status_code=400,
                detail="Mailbox username must be between 3 and 64 characters.",
            )

        if not re.fullmatch(
            r"[a-z0-9](?:[a-z0-9._-]{1,62}[a-z0-9])?",
            username,
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid mailbox username.",
            )

    payload = {
        "domain": domain.domain,
    }

    if username:
        payload["username"] = username

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{settings.tempmail_api}/api/v1/addresses",
                json=payload,
            )

    except httpx.HTTPError:
        raise HTTPException(
            status_code=502,
            detail="Unable to contact the tempmail backend.",
        )

    if response.status_code >= 400:
        try:
            upstream_error = response.json()
        except Exception:
            upstream_error = {}

        raise HTTPException(
            status_code=502,
            detail=upstream_error.get(
                "detail",
                "Upstream mailbox creation failed.",
            ),
        )

    try:
        upstream = response.json()
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Invalid response from tempmail backend.",
        )

    email = upstream.get("email")
    token = upstream.get("token")

    if not email or not token:
        raise HTTPException(
            status_code=502,
            detail="Tempmail backend returned an invalid mailbox response.",
        )

    existing = (
        db.query(Mailbox)
        .filter(Mailbox.email == email)
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Mailbox already exists.",
        )

    mailbox = Mailbox(
        email=email,
        tempmail_token=token,
        mailbox_type=MailboxType.ADMIN.value,
        user_id=None,
        guest_session_id=None,
        domain_id=domain.id,
        country=country,
        country_code=country_code,
        expires_at=None,
        is_active=True,
    )

    db.add(mailbox)

    db.add(
        Activity(
            user_id=current_admin.id,
            event="admin_mailbox_created",
            country=country,
            country_code=country_code,
            metadata_json={
                "mailbox": email,
                "domain": domain.domain,
                "mailbox_type": MailboxType.ADMIN.value,
            },
        )
    )

    db.commit()
    db.refresh(mailbox)

    return {
        "id": mailbox.id,
        "email": mailbox.email,
        "domain": domain.domain,
        "country": mailbox.country,
        "country_code": mailbox.country_code,
        "mailbox_type": mailbox.mailbox_type,
        "expires_at": mailbox.expires_at,
        "is_active": mailbox.is_active,
    }
 
 
@app.post("/api/admin/domains")
def create_admin_domain(
    request: CreateDomainRequest,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    domain = normalize_domain(request.domain)

    if not domain:
        raise HTTPException(
            status_code=400,
            detail="Domain is required.",
        )

    if len(domain) > 255:
        raise HTTPException(
            status_code=400,
            detail="Domain is too long.",
        )

    if "@" in domain or " " in domain:
        raise HTTPException(
            status_code=400,
            detail="Invalid domain.",
        )

    existing = (
        db.query(Domain)
        .filter(Domain.domain == domain)
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Domain already exists.",
        )

    verification_token = (
        "tempmail-"
        + secrets.token_urlsafe(32)
    )

    new_domain = Domain(
        domain=domain,
        status=DomainStatus.PENDING.value,
        verification_token=verification_token,
    )

    db.add(new_domain)
    db.flush()

    db.add(
        Activity(
            user_id=current_admin.id,
            event="admin_domain_created",
            metadata_json={
                "domain": domain,
                "domain_id": new_domain.id,
            },
        )
    )

    db.commit()
    db.refresh(new_domain)

    dns_records = get_dns_records(domain)

    dns_records["verification"]["value"] = (
        verification_token
    )

    return {
        "id": new_domain.id,
        "domain": new_domain.domain,
        "status": new_domain.status,
        "created_at": new_domain.created_at,
        "dns": dns_records,
    }
    
@app.post("/api/admin/domains/{domain_id}/verify")
async def verify_admin_domain(
    domain_id: int,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    domain = (
        db.query(Domain)
        .filter(Domain.id == domain_id)
        .first()
    )

    if not domain:
        raise HTTPException(
            status_code=404,
            detail="Domain not found.",
        )

    if domain.status == DomainStatus.DISABLED.value:
        raise HTTPException(
            status_code=400,
            detail="Domain is disabled.",
        )

    expected_txt_name = (
        f"_tempmail-verification.{domain.domain}"
    )

    expected_mx_host = (
        f"mail.{domain.domain}"
    )

    # -----------------------------------------------------
    # DNS checks
    # -----------------------------------------------------

    txt_records = resolve_txt(
        expected_txt_name,
        domain.domain,
    )

    mx_records = resolve_mx(
        domain.domain,
    )

    a_records = resolve_a(
        expected_mx_host,
    )

    expected_txt = (
        (domain.verification_token or "")
        .strip()
    )

    normalized_txt_records = {
        value.strip()
        for value in txt_records
    }

    txt_verified = (
        bool(expected_txt)
        and expected_txt in normalized_txt_records
    )

    mx_verified = any(
        host.rstrip(".").lower()
        == expected_mx_host.lower()
        and priority == 10
        for host, priority in mx_records
    )

    a_verified = (
        "2.25.196.198" in a_records
    )

    dns_checks = {
        "txt": txt_verified,
        "mx": mx_verified,
        "a": a_verified,
    }

    # DNS must pass before upstream provisioning.
    if not all(dns_checks.values()):
        return {
            "verified": False,
            "status": domain.status,
            "checks": {
                "dns": dns_checks,
                "upstream": False,
            },
            "dns": {
                "txt": txt_records,
                "mx": mx_records,
                "a": a_records,
            },
            "message": "DNS configuration is incomplete.",
        }

    # -----------------------------------------------------
    # Provision upstream mail server
    # -----------------------------------------------------

    provisioning = await provision_upstream_domain(
        domain.domain,
    )

    if not provisioning.get("success"):
        raise HTTPException(
            status_code=502,
            detail="Domain provisioning failed.",
        )

    # -----------------------------------------------------
    # Confirm upstream knows about the domain
    # -----------------------------------------------------

    try:
        async with httpx.AsyncClient(
            timeout=15.0
        ) as client:
            response = await client.get(
                f"{settings.tempmail_api.rstrip('/')}/api/v1/domains"
            )

        response.raise_for_status()
        upstream_data = response.json()

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Could not contact upstream mail API: "
                f"{exc}"
            ),
        )

    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Upstream mail API returned HTTP "
                f"{exc.response.status_code}."
            ),
        )

    upstream_domains = upstream_data.get(
        "domains",
        [],
    )

    upstream_verified = any(
        str(item).strip().lower().rstrip(".")
        == domain.domain.lower().rstrip(".")
        for item in upstream_domains
    )

    if not upstream_verified:
        raise HTTPException(
            status_code=502,
            detail=(
                "DNS verification passed, but the domain "
                "was not found in the upstream mail server."
            ),
        )

    # -----------------------------------------------------
    # Only now mark the domain verified
    # -----------------------------------------------------

    domain.status = DomainStatus.VERIFIED.value
    domain.verified_at = utcnow()

    db.add(
        Activity(
            user_id=current_admin.id,
            event="admin_domain_verified",
            metadata_json={
                "domain": domain.domain,
                "domain_id": domain.id,
                "dns_checks": dns_checks,
                "upstream_verified": True,
            },
        )
    )

    db.commit()
    db.refresh(domain)

    return {
        "verified": True,
        "id": domain.id,
        "domain": domain.domain,
        "status": domain.status,
        "verified_at": domain.verified_at,
        "checks": {
            "dns": dns_checks,
            "upstream": True,
        },
        "dns": {
            "txt": txt_records,
            "mx": mx_records,
            "a": a_records,
        },
        "provisioning": {
            "success": True,
        },
    }
    
@app.post("/api/admin/domains/{domain_id}/disable")
def disable_admin_domain(
    domain_id: int,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    domain = (
        db.query(Domain)
        .filter(Domain.id == domain_id)
        .first()
    )

    if not domain:
        raise HTTPException(
            status_code=404,
            detail="Domain not found.",
        )

    if domain.status == DomainStatus.DISABLED.value:
        raise HTTPException(
            status_code=400,
            detail="Domain is already disabled.",
        )

    if domain.status != DomainStatus.VERIFIED.value:
        raise HTTPException(
            status_code=400,
            detail=(
                "Only verified domains can be disabled."
            ),
        )

    domain.status = DomainStatus.DISABLED.value

    db.add(
        Activity(
            user_id=current_admin.id,
            event="admin_domain_disabled",
            metadata_json={
                "domain": domain.domain,
                "domain_id": domain.id,
                "previous_status": DomainStatus.VERIFIED.value,
            },
        )
    )

    db.commit()
    db.refresh(domain)

    return {
        "id": domain.id,
        "domain": domain.domain,
        "status": domain.status,
    }
    
    
@app.post("/api/admin/domains/{domain_id}/enable")
def enable_admin_domain(
    domain_id: int,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    domain = (
        db.query(Domain)
        .filter(Domain.id == domain_id)
        .first()
    )

    if not domain:
        raise HTTPException(
            status_code=404,
            detail="Domain not found.",
        )

    if domain.status != DomainStatus.DISABLED.value:
        raise HTTPException(
            status_code=400,
            detail="Domain is not disabled.",
        )

    domain.status = DomainStatus.PENDING.value
    domain.verified_at = None

    db.add(
        Activity(
            user_id=current_admin.id,
            event="admin_domain_enabled",
            metadata_json={
                "domain": domain.domain,
                "domain_id": domain.id,
                "previous_status": DomainStatus.DISABLED.value,
                "new_status": DomainStatus.PENDING.value,
            },
        )
    )

    db.commit()
    db.refresh(domain)

    return {
        "id": domain.id,
        "domain": domain.domain,
        "status": domain.status,
    }