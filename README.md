# Bus 4 Cantons

Appli (PWA) : prochains bus **lignes 854 et 870**, **Bouvines Église / Tournebride ⇄ 4 Cantons**, sans rien sélectionner.

- Horaires théoriques : GTFS de la Région Hauts-de-France (réseau interurbain Nord, périmètre 2), `build_data.py` → `data.json`.
  Ces lignes n'ont pas de temps réel publié.
- Mise à jour automatique des horaires chaque jour (GitHub Actions).

## Mise en ligne gratuite (GitHub Pages) — une seule fois

1. Créer un compte sur https://github.com (gratuit).
2. Nouveau dépôt **public** nommé `bus-4cantons` → « Add file > Upload files », y glisser **tout le contenu de ce dossier**
   (y compris le dossier caché `.github`, sinon voir l'option « ligne de commande » ci-dessous).
3. Dépôt > Settings > Pages > **Source : GitHub Actions**.
4. Onglet Actions > « Mise à jour des horaires et publication » > Run workflow.
5. L'adresse sera `https://<votre-pseudo>.github.io/bus-4cantons/`.

## Installation sur Android

Ouvrir l'adresse dans **Chrome** → menu ⋮ → **Installer l'application** (ou « Ajouter à l'écran d'accueil »).
L'icône apparaît comme une appli normale, en plein écran.

## Ligne de commande (alternative)

```
git init -b main
git add -A && git commit -m "Première version"
git remote add origin https://github.com/<pseudo>/bus-4cantons.git
git push -u origin main
```

## Test en local

`python -m http.server 8765` puis http://localhost:8765
