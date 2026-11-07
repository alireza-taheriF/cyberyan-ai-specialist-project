# گزارش تحلیل گراف ارتباطی و خوشه‌بندی نقش‌ها

> **داده‌ی ناقص:** برای این پروفایل‌ها بخشی پیدا نشد و تحلیل بدون آن انجام شد: Yacine Jernite.

## ۱. خلاصه شبکه

| شاخص | مقدار |
| :--- | :---: |
| منبع داده | `live` |
| سازمان | `Hugging Face` |
| تعداد گره‌ها | `10` |
| تعداد یال‌ها | `10` |
| چگالی گراف | `0.2222` |
| میانگین درجه | `2.00` |
| تعداد خوشه‌ها (k) | `5` |
| Silhouette | `0.1016` |

## ۲. افراد کلیدی (Centrality)

| رتبه | شناسه | نام | نقش | خوشه | Degree | Betweenness | Eigenvector | PageRank | امتیاز ترکیبی |
| :---: | :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | `p01` | Clem Delangue 🤗 | Co-founder & CEO | `C0` | `0.4444` | `1.0000` | `1.0000` | `0.2214` | **`0.8333`** |
| 2 | `p02` | Julien Chaumond | Co-founder | `C0` | `0.3333` | `0.9091` | `0.9748` | `0.1457` | **`0.7025`** |
| 3 | `p05` | Merve Noyan | Machine Learning Engineer | `C2` | `0.3333` | `0.6364` | `0.3629` | `0.1035` | **`0.4433`** |
| 4 | `p09` | David Holtz | Machine Learning Ops Engineer | `C4` | `0.2222` | `0.3636` | `0.4517` | `0.0968` | **`0.3579`** |
| 5 | `p03` | Thomas Wolf | Co-founder - Chief Science Officer | `C1` | `0.2222` | `0.0000` | `0.6558` | `0.0888` | **`0.3108`** |
| 6 | `p04` | Lysandre Debut | COSO | `C1` | `0.2222` | `0.3636` | `0.1622` | `0.1093` | **`0.2969`** |
| 7 | `p07` | Yacine Jernite | Head of Machine Learning and Society | `C3` | `0.1111` | `0.0000` | `0.5368` | `0.0595` | **`0.2212`** |
| 8 | `p06` | Sayak Paul | Senior Research Engineer | `C2` | `0.1111` | `0.0000` | `0.1942` | `0.0425` | **`0.1203`** |
| 9 | `p08` | Sergio Paniego Blanco | Machine Learning Engineer | `C2` | `0.1111` | `0.0000` | `0.0638` | `0.0755` | **`0.1175`** |
| 10 | `p10` | Philipp Schmid | Staff Engineer (Developer Experience & Developer Relations) | `C4` | `0.1111` | `0.0000` | `0.1187` | `0.0570` | **`0.1145`** |

برداشت‌ها:

- **بیشترین امتیاز ترکیبی:** `Clem Delangue 🤗` با `0.8333`.
- **قوی‌ترین پل ارتباطی (Betweenness):** `Clem Delangue 🤗`.
- **بیشترین ارتباط مستقیم (Degree):** `Clem Delangue 🤗`.
- **بیشترین نفوذ از طریق افراد پرنفوذ (Eigenvector):** `Clem Delangue 🤗`.
- **بدون نقش پل (Betweenness صفر):** Thomas Wolf، Yacine Jernite، Sayak Paul، Sergio Paniego Blanco، Philipp Schmid.

**حساسیت Betweenness به تعریف فاصله:** d=1/W: Clem Delangue 🤗 | d=1/W^2: Clem Delangue 🤗 | d=1/W^2.5: Clem Delangue 🤗. اگر این نام‌ها متفاوت باشند، نقش «پل» به تعریف فاصله وابسته است و نباید قطعی تلقی شود.

## ۳. قوی‌ترین پیوندها در گراف ارتباطی

وزن‌های به‌کاررفته: activity=`0.45`، company=`0.25`، skills=`0.2`، education=`0.1`.

| رتبه | فرد اول | فرد دوم | وزن | Activity | شرکت | مهارت (Jaccard) | شرکت‌های مشترک |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| 1 | Clem Delangue 🤗 | Julien Chaumond | **`0.6956`** | `1.0000` | `0.3500` | `0.2903` | Hugging Face |
| 2 | Lysandre Debut | Sergio Paniego Blanco | **`0.5483`** | `1.0000` | `0.3500` | `0.0538` | Hugging Face |
| 3 | Clem Delangue 🤗 | Thomas Wolf | **`0.4683`** | `0.8462` | `0.3500` | `0.0000` | Hugging Face |
| 4 | Clem Delangue 🤗 | Yacine Jernite | **`0.4683`** | `0.8462` | `0.3500` | `0.0000` | Hugging Face |
| 5 | David Holtz | Philipp Schmid | **`0.3665`** | `0.4231` | `0.6500` | `0.0682` | Hugging Face |
| 6 | Clem Delangue 🤗 | David Holtz | **`0.3506`** | `0.5769` | `0.3500` | `0.0172` | Hugging Face |
| 7 | Lysandre Debut | Merve Noyan | **`0.2936`** | `0.4231` | `0.3500` | `0.0784` | Hugging Face |
| 8 | Thomas Wolf | Merve Noyan | **`0.2862`** | `0.4231` | `0.3500` | `0.0417` | Hugging Face |
| 9 | Julien Chaumond | Merve Noyan | **`0.2779`** | `0.4231` | `0.3500` | `0.0000` | Hugging Face |
| 10 | Julien Chaumond | Sayak Paul | **`0.2779`** | `0.4231` | `0.3500` | `0.0000` | Hugging Face |

## ۴. خوشه‌بندی نقش‌ها و مهارت‌ها

مقدار k با بیشینه‌کردن Silhouette انتخاب شد (k=3: `0.0993`، k=4: `0.0986`، k=5: `0.1016`). مقدار نهایی `0.1016` یعنی: ساختار خوشه‌ای ضعیف؛ خوشه‌ها را باید گرایش کلی دانست، نه مرز قطعی.

| خوشه | عنوان (مهارت‌های متمایزکننده) | اعضا | میانگین شباهت درونی | مهارت‌های پرتکرار |
| :---: | :--- | :--- | :---: | :--- |
| `C0` | Cluster 0: Business Development, Business Strategy, E-commerce | Clem Delangue 🤗، Julien Chaumond | `0.4106` | Business Development، Business Strategy، E-commerce، Entrepreneurship، Marketing، Mobile Devices |
| `C1` | Cluster 1: Machine Learning, Deep Learning, Gestion de projet | Thomas Wolf، Lysandre Debut | `0.0950` | Deep Learning، Machine Learning، Python، Artificial Intelligence، C، Data Science |
| `C2` | Cluster 2: PyTorch, SQL, Deep Learning | Merve Noyan، Sayak Paul، Sergio Paniego Blanco | `0.1286` | Deep Learning، Google Cloud، PyTorch، Python، SQL، Computer vision |
| `C3` | Cluster 3: no skills listed (grouped by role and activity) | Yacine Jernite | — |  |
| `C4` | Cluster 4: Microsoft Azure, Amazon Web Services (AWS), Google Cloud | David Holtz، Philipp Schmid | `0.1262` | Amazon Web Services (AWS)، Google Cloud، Microsoft Azure، Artificial Intelligence، Big Data، C |

### جفت‌مهارت‌های پرتکرار

| رتبه | جفت مهارت | تعداد پروفایل |
| :---: | :--- | :---: |
| 1 | Deep Learning + Python | `5` |
| 2 | Google Cloud + Python | `4` |
| 3 | Machine Learning + Python | `4` |
| 4 | Amazon Web Services (AWS) + Google Cloud | `3` |
| 5 | C + Python | `3` |
| 6 | Deep Learning + Git | `3` |
| 7 | Deep Learning + Google Cloud | `3` |
| 8 | Deep Learning + Java | `3` |

## ۵. محدودیت‌ها

- ضرایب وزن یال و امتیاز ترکیبی انتخاب طراحی‌اند و از داده یاد گرفته نشده‌اند.
- با ۱۰ پروفایل، رتبه‌ها و خوشه‌ها آماری نیستند و با تغییر کوچک داده ممکن است عوض شوند.
- تصویر این نتایج در `output/graph.png` است: گراف، مقایسه‌ی شاخص‌ها و ماتریس شباهت TF-IDF.
