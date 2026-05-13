"""
Central settings — loaded from .env file.
All modules import `settings` from here.
Designed for easy migration: change DATABASE_URL to PostgreSQL in .env only.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────────
    app_name: str = "Patabrava"
    app_tagline: str = "Captação de imóveis · Lisboa & Cascais"
    app_env: str = "development"
    log_level: str = "INFO"
    log_file: str = "logs/patabrava.log"

    # Outreach message signature — appended to auto-drafted contact
    # messages in the dashboard. Per-tenant configuration.
    contact_signature: str = "Equipa Patabrava · AMI 23783"

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = f"sqlite:///{ROOT_DIR}/data/patabrava.db"

    # ── Proxy ────────────────────────────────────────────────────────────────
    use_proxies: bool = False
    proxy_list: str = ""

    @property
    def proxies(self) -> List[str]:
        if not self.proxy_list:
            return []
        return [p.strip() for p in self.proxy_list.split(",") if p.strip()]

    # ── Scraping ─────────────────────────────────────────────────────────────
    # Doubled on 2026-05-08 to reduce bot fingerprint and ride out
    # transient rate-limits without escalating to a hard IP block. With
    # the lower async-fetcher concurrency (3), per-zone wall-time still
    # lands inside 5-8 min on a typical Lisboa freguesia.
    scrape_delay_min: float = 4.0
    scrape_delay_max: float = 10.0
    max_retries: int = 3
    request_timeout: int = 30
    headless_browser: bool = True

    # ── Zones ────────────────────────────────────────────────────────────────
    # Patabrava — agência sediada em Alvalade. Objectivo do scrapper:
    # encontrar PROPRIETÁRIOS DIRECTOS (FSBO) com telefone — máximo de leads.
    # Cobertura ampla: Lisboa cidade + 22 freguesias + Linha de Cascais +
    # Sintra + Oeiras + Margem Sul. As freguesias de Lisboa aparecem como
    # sweeps paralelos para apanhar a tail acima do cap de 1000 da query
    # municipal.  Slugs validados em scrapers/imovirtual.py:99.
    target_zones: str = (
        "Lisboa,"
        "Lisboa-Alvalade,Lisboa-Areeiro,Lisboa-Arroios,"
        "Lisboa-Avenidas-Novas,Lisboa-Beato,Lisboa-Belem,Lisboa-Benfica,"
        "Lisboa-Campo-de-Ourique,Lisboa-Campolide,Lisboa-Carnide,"
        "Lisboa-Estrela,Lisboa-Lumiar,Lisboa-Marvila,Lisboa-Misericordia,"
        "Lisboa-Olivais,Lisboa-Parque-das-Nacoes,Lisboa-Penha-de-Franca,"
        "Lisboa-Santa-Clara,Lisboa-Santa-Maria-Maior,Lisboa-Santo-Antonio,"
        "Lisboa-Sao-Domingos-de-Benfica,Lisboa-Sao-Vicente,"
        "Cascais,Sintra,Oeiras,Amadora,Loures,Odivelas,Mafra,"
        "Almada,Seixal,Sesimbra,Barreiro,Montijo,Setubal,"
        # Tier 1 luxury getaway (Sprint 2026-05-13):
        #   Grandola → cobre Comporta + Melides (municipality slug)
        #   Ericeira → sub-Mafra com nome próprio nos portais
        #   Costa-da-Caparica → sub-Almada
        "Grandola,Ericeira,Costa-da-Caparica"
    )

    @property
    def zones(self) -> List[str]:
        return [z.strip() for z in self.target_zones.split(",") if z.strip()]

    # ── Scheduler ────────────────────────────────────────────────────────────
    schedule_time: str = "08:00"
    schedule_enabled: bool = True

    # ── Scoring ──────────────────────────────────────────────────────────────
    hot_score_threshold: int = 60
    warm_score_threshold: int = 40

    # ── Email Alerts ─────────────────────────────────────────────────────────
    alert_email_enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    alert_email_to: str = ""

    # ── Telegram Alerts ──────────────────────────────────────────────────────
    alert_telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # ── Derived paths ────────────────────────────────────────────────────────
    @property
    def data_dir(self) -> Path:
        p = ROOT_DIR / "data"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def logs_dir(self) -> Path:
        p = ROOT_DIR / "logs"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


settings = Settings()
