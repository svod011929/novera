# Branded installer — short ops note

**Для новичка:** дважды кликните `СОБРАТЬ_БОТА.bat` в корне проекта.  
Полная инструкция: `_owner_inputs/BRAND_PROFILES/README.md`.

## Что делает wizard

1. Спрашивает имя / слоган / домен / IP / Telegram ID / логотип / цвет
2. Сам пишет `_owner_inputs/BRAND_PROFILES/<id>/profile.json` + `assets/logo.jpg`
3. Вызывает `scripts/build_bootstrap_installer.ps1 -BrandProfile <id>`
4. Печатает крупные шаги: куда `.sh`, WinSCP, одна команда на VPS, BotFather

Секреты (bot token, RPC/WSS, seed, runtime key) **не** запекаются.

## Advanced

```powershell
powershell -NoProfile -File scripts\build_bootstrap_installer.ps1 -BrandProfile novera
```
