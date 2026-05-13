# Sonraki düzenleme planı (XYZ / tenant odaklı)

Önceki tartışmadaki istekler **bağımlılık ve risk** sırasına göre 6 adımda gruplanmıştır. Her adım bir öncekinin üzerine inşa eder.

---

## 1 — Tenant bazlı agent yapılandırması (veri + admin + uygulama)

**Amaç:** XYZ gibi tek hastanede bile “bu tenant için temperature, model, max history, hangi tool’lar açık” gibi ayarların **DB’den** yönetilmesi; admin panelden düzenlenebilmesi.

**Kapsam:** `Tenant.settings` veya ayrı bir config alanı; şema (bilinen anahtarlar, `extra=forbid`); `GET/PATCH` admin API; chat isteğinde bu değerlerle LLM/RAG profilinin seçilmesi (global `.env` varsayılan, tenant override).

**Çıktı:** Admin’den kaydedilen ayarlar gerçek sohbet akışında etkili olur.

---

## 2 — Randevu / HIS tool çıktısı ve kullanıcıya yansıma kalitesi

**Amaç:** Dış hastane API’sinden gelen **boş liste, slot dolu, servis dışı, ağ hatası** durumlarında agent’ın tutarlı ve anlaşılır cevap vermesi.

**Kapsam:** `list_available_slots_tool` (ve ilgili connector) için **sabitlenmiş sonuç şeması**; graph tarafında tool hata/boş sonuç → **açık kullanıcı mesajı** (şablon veya küçük bir “cevap üret” düğümü); gerekirse kısa sistem prompt güncellemesi.

**Çıktı:** “Saat uygun mu?” sorusuna HIS yanıtına göre güvenilir davranış.

---

## 3 — Ticket / randevu durumu sorma (oturum + referans + güvenli kimlik)

**Amaç:** Yeni sohbette bile kullanıcının **kendi** ticket/randevu durumunu sorabilmesi; mümkünse **referans kodu** ile; kimlik ile sorgu **doğrulama** olmadan genişletilmez.

**Kapsam:** Chat için `get_ticket_status_by_reference` benzeri tool (yalnızca JWT’deki kullanıcının ticket’ı); randevu tarafında aynı mantık veya “liste zaten user_id ile” akışının netleştirilmesi; **isteğe bağlı** ikinci faz: OTP / ek alan ile sınırlı kimlik doğrulama (ayrı tasarım dokümanı).

**Çıktı:** Referans + giriş yapmış hasta senaryosu üretimde güvenli şekilde çalışır.

---

## 4 — Dış sistem çağrıları için asenkron katman (ihtiyaca göre)

**Amaç:** HIS yanıt süreleri uzun veya yüksek olduğunda **HTTP senkron** yerine veya yanında kuyruk tabanlı işleyiş; bildirimlerle uyum.

**Kapsam:** Hangi işlemlerin senkron kalacağı / kuyruğa alınacağı kararı; mevcut **Celery** ile “slot sorgusu” veya “rezervasyon teyidi” için worker pattern; RabbitMQ yalnızca **çoklu consumer / yönlendirme** gerekiyorsa ayrı değerlendirme (infra maliyeti).

**Çıktı:** Dokümante edilmiş bir “senkron vs async” sınırı ve en az bir kritik akış kuyrukta doğrulanmış örnek.

---

## 5 — `agent/` paket yapısının okunabilir hale getirilmesi

**Amaç:** `graph.py` içinde biriken mantığın **modüllere** ayrılması; ileride retriever / ek düğümler eklenecekse yer açılması.

**Kapsam:** Örn. `hospitai_agent/graph/` (`state`, `nodes`, `edges`, `streaming`) veya benzeri ince dilimleme; davranış değişmeden taşıma; kısa **`docs/AGENT.md`** (akış + dosya haritası).

**Çıktı:** Yeni geliştirici “retriever nerede?” diye sormadan haritayı okuyabilir.

---

## 6 — Doğrulama, gözlem ve geri dönüş

**Amaç:** Yukarıdaki değişikliklerin regresyon yaratmaması.

**Kapsam:** Kritik yollar için entegrasyon testi (tenant config + bir chat tool senaryosu); yapılandırılmış log / metrik için bir sonraki adımın net listesi (Prometheus vb. isteğe bağlı).

**Çıktı:** CI’da güvenen en az bir “tenant + chat” senaryosu; planlanan observability maddeleri tek sayfada.

---

## Özet sıra

| Sıra | Konu                                                          |
| ---: | ------------------------------------------------------------- |
|    1 | Tenant agent config (temel)                                   |
|    2 | HIS / slot cevap kalitesi                                     |
|    3 | Ticket & randevu sorgu (referans + güvenli kimlik politikası) |
|    4 | Async / kuyruk (gerektiğinde)                                 |
|    5 | Agent kod düzeni                                              |
|    6 | Test + gözlem                                                 |

İstersen bir sonraki adımda yalnızca **1** veya **1+2** için teknik alt görev listesi (API şeması + dosya listesi) çıkarılabilir.
