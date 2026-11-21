# Nextcloud Home Server
![Nextcloud and antiX Linux](NextCloudHomeServer.png#width=5%)
## Project Overview

I built a self-hosted Nextcloud server on AntiX Linux to create a private cloud storage platform similar to Google Drive. The goal was to learn Linux server administration, web hosting, database management, networking, and self-hosted infrastructure while building a practical system that I could use daily.

The final solution provides file storage, synchronization, web access, and remote connectivity while keeping all data under my control.

---

## The Problem

Cloud storage services are convenient, but they require trusting third-party providers with personal files and data. I wanted to understand how cloud platforms operate behind the scenes and gain hands-on experience building and managing my own infrastructure.

To achieve this, I needed to:

* Build a complete server environment
* Deploy a web application
* Configure a database backend
* Enable secure remote access
* Troubleshoot deployment and configuration issues
* Manage storage resources

---

## Notes Before Installation

This project was built on an **HP Pavilion laptop that is over 10 years old with only 2 GB of RAM**. Due to the limited hardware resources, **AntiX Linux** was chosen because it is an extremely lightweight distribution that performs well on older machines while still providing everything needed to run a LAMP stack and Nextcloud.

Although this README documents the overall installation process and the commands I used, **your commands may differ depending on your Linux distribution, package manager, PHP version, or Apache configuration**. Debian, Ubuntu, AntiX, Fedora, Arch, and other distributions often use different package names and setup procedures.

For anyone following this project, I highly recommend watching this excellent one-hour tutorial alongside the README, as it explains the installation process in detail and covers distribution-specific differences:

**YouTube Tutorial:** https://youtu.be/TGsGalCOl2k?si=MQMHTdmqwoBVtFUD

This README should be viewed as a case study documenting how I built the project on my own system rather than as a universal installation guide.

---

## Solution Architecture

The solution was built using the following technologies:

### Operating System

* AntiX Linux

### Web Server

* Apache2

### Backend Runtime

* PHP

### Database

* MariaDB

### Cloud Platform

* Nextcloud

### Remote Access

* Tailscale

### Architecture

```text
Client Devices
      │
      ▼
Local Network / Tailscale
      │
      ▼
Apache2
      │
      ▼
PHP
      │
      ▼
Nextcloud
      │
      ▼
MariaDB
      │
      ▼
Data Storage
```

---

# Installation Process

## 1. Update System

```bash
sudo apt update
sudo apt upgrade -y
```

---

## 2. Install Apache

Apache serves the Nextcloud web application.

```bash
sudo apt install apache2 -y
```

Enable and start Apache:

```bash
sudo systemctl enable apache2
sudo systemctl start apache2
```

Verify installation:

```bash
sudo systemctl status apache2
```

Test locally:

```bash
curl -I http://localhost
```

---

## 3. Install PHP and Required Modules

Nextcloud requires several PHP extensions.

Install PHP:

```bash
sudo apt install php php-cli php-common -y
```

Install required modules:

```bash
sudo apt install php-mysql -y
sudo apt install php-xml -y
sudo apt install php-gd -y
sudo apt install php-curl -y
sudo apt install php-zip -y
sudo apt install php-mbstring -y
sudo apt install php-intl -y
```

Verify installation:

```bash
php -m | grep -E "curl|zip|gd|xml|mbstring|intl"
```

Restart Apache:

```bash
sudo systemctl restart apache2
```

---

## 4. Install MariaDB

MariaDB is used as Nextcloud's database backend.

```bash
sudo apt install mariadb-server -y
```

Secure installation:

```bash
sudo mysql_secure_installation
```

Enable and start MariaDB:

```bash
sudo systemctl enable mariadb
sudo systemctl start mariadb
```

Verify status:

```bash
sudo systemctl status mariadb
```

---

## 5. Create Nextcloud Database

Login to MariaDB:

```bash
sudo mysql
```

Create database and user:

```sql
CREATE DATABASE nextcloud;

CREATE USER 'nextclouduser'@'localhost'
IDENTIFIED BY 'StrongPassword';

GRANT ALL PRIVILEGES
ON nextcloud.*
TO 'nextclouduser'@'localhost';

FLUSH PRIVILEGES;

EXIT;
```

---

## 6. Download Nextcloud

Move to web root:

```bash
cd /var/www/html
```

Download latest release:

```bash
sudo wget https://download.nextcloud.com/server/releases/latest.zip
```

Install unzip:

```bash
sudo apt install unzip -y
```

Extract archive:

```bash
sudo unzip latest.zip
```

---

## 7. Configure Permissions

Set correct ownership:

```bash
sudo chown -R www-data:www-data /var/www/html/nextcloud
```

Set permissions:

```bash
sudo chmod -R 755 /var/www/html/nextcloud
```

---

## 8. Configure Apache Modules

Enable required modules:

```bash
sudo a2enmod rewrite
sudo a2enmod headers
```

Restart Apache:

```bash
sudo systemctl restart apache2
```

---

## 9. Complete Nextcloud Setup

Open:

```text
http://localhost/nextcloud
```

or

```text
http://SERVER-IP/nextcloud
```

Configure:

* Administrator account
* Database name
* Database username
* Database password
* Data directory

---

## 10. Configure Trusted Domains

Edit configuration:

```bash
sudo nano /var/www/html/nextcloud/config/config.php
```

Example:

```php
'trusted_domains' =>
array (
  0 => 'localhost',
  1 => '192.168.1.10',
  2 => '100.x.x.x',
),
```

This allows access from both local network and Tailscale addresses.

---

## 11. Configure Remote Access

Install Tailscale:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
```

Authenticate:

```bash
sudo tailscale up
```

Verify status:

```bash
tailscale status
```

---

# Troubleshooting

### Apache Logs

```bash
sudo tail -f /var/log/apache2/error.log
```

### Check Listening Ports

```bash
sudo ss -tlnp
```

### Verify DNS Resolution

```bash
nslookup apps.nextcloud.com
```

### Test Internet Connectivity

```bash
ping google.com
```

### Check Storage

```bash
df -h
```

### Check Nextcloud Data Size

```bash
du -sh /var/www/html/nextcloud/data
```

---

# Challenges Encountered

## Missing PHP Modules

During deployment, Nextcloud reported several missing dependencies including:

* XML
* mbstring
* ZIP
* GD
* cURL

These modules were installed manually and verified through PHP module checks.

---

## HTTP 500 Errors

The application initially produced server errors due to missing PHP dependencies. Apache logs were used to identify and resolve the issues.

---

## Trusted Domain Restrictions

Nextcloud blocked access from certain addresses until trusted domains were configured correctly.

---

## Remote Connectivity

Remote access required validating DNS resolution, outbound connectivity, and Tailscale configuration.

---

# Results

The completed platform provides:

* Self-hosted cloud storage
* File upload and download
* Web-based file management
* User authentication
* Local network access
* Remote access through Tailscale
* Centralized file storage

### Current Storage

| Metric            | Value  |
| ----------------- | ------ |
| Total Storage     | 293 GB |
| Used Storage      | 11 GB  |
| Available Storage | 267 GB |

---

# Skills Demonstrated

* Linux Administration
* Apache Configuration
* PHP Environment Setup
* MariaDB Administration
* Self-Hosted Infrastructure
* Networking
* DNS Troubleshooting
* Log Analysis
* Remote Access Configuration
* Storage Management
* System Debugging

---

# Future Improvements

* HTTPS with SSL certificates
* Automated backups
* Multi-user deployment
* External storage integration
* Reverse proxy configuration
* Monitoring and alerting

---

## Author

Ahmed Sarhan

Portfolio: [www.ahmedsarhan.space](http://www.ahmedsarhan.space)
