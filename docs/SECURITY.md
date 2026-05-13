# HospitAI — güvenlik notları

Bu belge üretim öncesi güvenlik başlıklarını listeler; tıbbi uyumluluk (KVKK, HIPAA vb.) için ayrı hukuki ve süreç incelemesi gerekir.

## Kimlik ve yetkilendirme

- **JWT**: `JWT_SECRET` üretimde güçlü ve gizli tutulmalı; token süreleri `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` ile sınırlanır.
- **RBAC**: Admin uçları (`/api/v1/admin/...`) yalnızca `admin` rolü; doküman ingest/sil/reindex için `admin` veya `staff`.
- **İç servis**: `INTERNAL_API_KEY` tanımlıysa `X-Internal-Key` ile korunan iç uçlar kullanılır.

## Oran sınırı (auth)

- `POST /api/v1/auth/login`, `/register`, `/refresh` uçlarında **SlowAPI** ile IP başına limit uygulanır (varsayılan: 30/15/60 dakika başına). Aşımda **429** ve `error.code=rate_limited` döner.

## Hassas veri

- Sohbet güvenlik katmanı hassas kalıpları (ör. TC/kart) bloklamaya çalışır; tam PII maskeleme veya DLP entegrasyonu ayrı bir çalışmadır.
- **Tenant connector** API anahtarı veritabanında saklanır; admin API yanıtında yalnızca “anahtar var mı” bilgisi döner.

## Gözlemlenebilirlik

- Her istek için `http_request` structlog kaydı (yöntem, yol, status, süre ms) üretilir; üretimde log biriktirme ve erişim kontrolü tanımlanmalıdır.
- `X-Request-ID` yanıt başlığı ve hata gövdesinde `request_id` alanı vardır; destek ve korelasyon için istemciler aynı başlığı gönderebilir.

## Bağımlılıklar ve tedarik zinciri

- Python ve npm bağımlılıkları düzenli güncellenmeli; güvenlik taraması (Dependabot, `pip audit`, `npm audit`) önerilir.

## CORS

- `CORS_ORIGINS` üretimde yalnızca bilinen web kökenleriyle sınırlı olmalıdır.

## Celery

- Broker olarak Redis kullanılır; ağ erişimi ve şifreleme (TLS) ortam politikanıza göre yapılandırılmalıdır.
- Ticket oluşturma sonrası `notify_domain_event` kuyruğa atılır; broker yoksa uyarı log’lanır, HTTP yanıtı etkilenmez.
