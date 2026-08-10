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
- `MYSQL_HOST`: nom d'hôte MySQL local ou distant (`localhost` par défaut)
- `MYSQL_PORT`: port MySQL (`3306` par défaut)
- `MYSQL_USER`: utilisateur MySQL (`dashboard` par défaut)
- `MYSQL_PASSWORD`: mot de passe MySQL
- `MYSQL_DATABASE`: nom de la base MySQL (`canpack_isolation` par défaut)

Exemple pour Streamlit Cloud ou un autre service :
- `MQTT_BROKER = broker.hivemq.com`
- `MQTT_PORT = 1883`
- `MQTT_PREFIX = canpack`
- `MYSQL_HOST = localhost`
- `MYSQL_PORT = 3306`
- `MYSQL_USER = dashboard`
- `MYSQL_PASSWORD = <secret>`
- `MYSQL_DATABASE = canpack_isolation`

### Node-RED
Installez `node-red-node-mysql` dans Node-RED.
Configurez un noeud MySQL avec le même hôte et la même base que l'application Streamlit.
Les topics attendus par l'application sont de type :
- `canpack/bodymaker/dashboard`
- `canpack/laveuse/dashboard`
- `canpack/lsm/dashboard`

Le listener Python souscrit uniquement aux topics `/dashboard` pour éviter de mélanger les anciens topics de fuite.

### Schéma MySQL recommandé
```sql
CREATE TABLE readings (
  id INT AUTO_INCREMENT PRIMARY KEY,
  cabinet VARCHAR(50),
  courant_mA FLOAT,
  moyenne FLOAT,
  statut VARCHAR(20),
  horodatage DATETIME,
  INDEX idx_cabinet_time (cabinet, horodatage)
);

CREATE TABLE alerts (
  id INT AUTO_INCREMENT PRIMARY KEY,
  cabinet VARCHAR(50),
  niveau VARCHAR(20),
  valeur_mA FLOAT,
  horodatage DATETIME,
  INDEX idx_cabinet_time (cabinet, horodatage)
);
```

### Synchronisation / réplication
La synchronisation MySQL se fait idéalement via la réplication native MySQL/MariaDB.
Pour un usage local + cloud, la base locale peut être la source et la base distante la réplique.
Sinon, utilisez un script planifié qui envoie les nouvelles lignes vers la base distante quand la connectivité est disponible.

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
