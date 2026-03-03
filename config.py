from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str
    supabase_service_key: str

    google_calendar_id: str
    google_drive_root_folder_id: str
    gmail_sender: str
    gmail_internal_recipient: str

    webhook_secret: str


settings = Settings()
