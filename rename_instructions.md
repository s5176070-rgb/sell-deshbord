# שינוי שם תיקייה

הסשן הנוכחי (Claude Code) נועל את התיקייה כל עוד הוא פתוח.

## שלבים

1. סגור לגמרי את אפליקציית Claude Code (לא רק טרמינל אחד — את כל האפליקציה).
2. פתח PowerShell חדש והרץ:

```powershell
Rename-Item -Path "C:\Users\97252\SELL DESHBORD" -NewName "סיכוי לנפילה בשוק ההון"
```

3. אם עדיין נעול — בדוק מי מחזיק את התיקייה (דורש הורדת Sysinternals):

```powershell
handle.exe "SELL DESHBORD"
```

ואז סגור את התהליך שמוצג שם, לפני חזרה לשלב 2.

4. פתח את Claude Code מחדש בנתיב החדש:

```powershell
cd "C:\Users\97252\סיכוי לנפילה בשוק ההון"
```
