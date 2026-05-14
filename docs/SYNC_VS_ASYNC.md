# Senkron ve asenkron sınırı (dış HIS / kuyruk)

Bu belge [PLAN_SONRAKI_ADIMLAR.md](PLAN_SONRAKI_ADIMLAR.md) adım 4 çıktısıdır: hangi işlemler **sohbet isteği içinde senkron** kalır, hangileri **Celery** ile kuyruğa alınır.

## Özet tablo

| Akış                                           | Varsayılan            | Gerekçe                                                                                |
| ---------------------------------------------- | --------------------- | -------------------------------------------------------------------------------------- |
| Chat içi `list_available_slots` (dış HIS HTTP) | **Senkron**           | Kullanıcı tek yanıt bekler; mevcut LangGraph düğümü anında araç sonucu üretir.         |
| Chat içi ticket / randevu DB araçları          | **Senkron**           | Düşük gecikme; tenant + kullanıcı kapsamı zaten uygulanıyor.                           |
| RAG embedding yeniden hesaplama                | **Asenkron (Celery)** | Uzun CPU/IO; `reindex_document_embeddings` görevi.                                     |
| Alan olayı bildirimi (`notify_domain_event`)   | **Asenkron (Celery)** | Yan etki; API yanıtını bloklamaz.                                                      |
| Dış bağlantı “sağlık” probu (doktor listesi)   | **Asenkron (Celery)** | Opsiyonel yük / zaman aşımı; admin `POST …/tenant-connector/probe` ile kuyruğa alınır. |
| Harici randevu oluşturma (REST)                | **Senkron (API)**     | İstemci anında sonuç ister; ileride teyit web kancası Celery’ye taşınabilir.           |

## RabbitMQ

Şu an **Redis** broker + result backend yeterli. Çoklu consumer yönlendirme veya ayrı kuyruk topolojisi gerektiğinde RabbitMQ ayrı değerlendirilir (ek operasyon maliyeti).

## İlgili kod

- Celery uygulaması: `backend/src/hospitai/workers/celery_app.py`
- Görevler: `backend/src/hospitai/workers/tasks.py`
- Dış HIS HTTP: `backend/src/hospitai/infrastructure/hospital_connector.py`
