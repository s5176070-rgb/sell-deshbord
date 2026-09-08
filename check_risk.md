# בדיקת סיכוי לנפילה

הבדיקה כבר קיימת ב-`stress.py`. אין צורך בקוד חדש — רק להריץ:

```bash
python stress.py --bench
```

מדפיס טבלאות (MSS score, walk-forward, buckets) בלי לכתוב קובץ.

## אם רוצים דף HTML מלא

```bash
python stress.py --full
```

## אם רוצים לרענן נתונים קודם (מחירים + breadth)

```bash
python breadth.py
python stress.py --bench
```

## פלט אחרון (2026-09-04)

```
MSS 49.9  WATCH  5d +4.3  sell flag off
band 45-69: rate 17.48%  lift 1.11
```

סיכון בינוני, ללא איתות מכירה.
