# Canpack Isolement Dashboard

## À propos
Ce projet est une application Streamlit qui affiche les mesures d'isolement électrique de trois armoires (`Body Maker`, `Zone Laveuse`, `LSM (Vernissage)`). Les données sont reçues via MQTT dans `mqtt_listener.py` et stockées dans une base SQLite locale (`.canpack_data.db`).

## Déploiement Cloud
Dans un environnement cloud, le broker MQTT ne peut pas être `localhost`.
Le projet utilise une valeur par défaut publique : `broker.hivemq.com:1883`.

### Variables d'environnement recommandées
- `MQTT_BROKER`: nom d'hôte du broker MQTT externe
- `MQTT_PORT`: port MQTT (`1883` par défaut)
- `MQTT_PREFIX`: préfixe de topic MQTT (`canpack` par défaut)

Exemple pour Streamlit Cloud ou un autre service :
- `MQTT_BROKER = broker.hivemq.com`
- `MQTT_PORT = 1883`
- `MQTT_PREFIX = canpack`

### Node-RED
Configurez le broker MQTT de Node-RED pour utiliser le même broker externe.
Les topics attendus par l'application sont de type :
- `canpack/bodymaker/dashboard`
- `canpack/laveuse/dashboard`
- `canpack/lsm/dashboard`

Le listener Python souscrit uniquement aux topics `/dashboard` pour éviter de mélanger les anciens topics de fuite.

## Exécution locale
1. Installer les dépendances :
   ```bash
   pip install -r requirements.txt
   ```
2. Lancer l'application Streamlit :
   ```bash
   streamlit run app.py
   ```
3. Vérifier que Node-RED publie sur le broker MQTT configuré.

## Notes
- L'application Streamlit démarre un listener MQTT en arrière-plan via `mqtt_listener.py`.
- Si le broker ne peut pas être atteint, la page affiche une erreur claire avec le broker attendu.
