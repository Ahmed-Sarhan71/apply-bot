# Project Cards (business-benefit summaries)

Built from the project READMEs. Every number below comes from the README. If a README gives no figure, the card says so instead of guessing.
Each card ends with "Do not claim", the limits the email writer must respect.

---

## 1. AI Research Assistant (private document Q&A)
**Tech:** Python, FastAPI, Streamlit, Qdrant (vector DB), Ollama (llama3.1:8b + nomic-embed-text), RAG
**Problem:** Teams lose time searching long PDFs for answers, and cloud AI tools mean sending confidential documents to a third party.
**Solution:** A RAG app where users upload PDFs and ask questions in a chat interface, with answers drawn from the documents and filterable by source. It runs entirely offline on local models.
**Business benefit:** Documents never leave the company's own machines, which suits sensitive material. Because inference is local, there are no per-question API fees. Staff get answers in seconds instead of reading whole documents.
**Cost:** Open-source stack only (Ollama, Qdrant, FastAPI, Streamlit). No cloud or API bill stated or needed.
**Do not claim:** Production users, accuracy metrics, or scale. The README lists none.

## 2. Candy Calorie Counter (computer-vision counting)
**Tech:** Python, YOLO11s (Ultralytics), OpenCV, Streamlit, Google Colab (T4) for training
**Problem:** Counting items and totalling their nutrition by hand is slow and error-prone.
**Solution:** A custom-trained detector that identifies 5 product types in photos, video or a live camera and totals calories and sugar automatically. It has a live web demo, and the model can be exported for Raspberry Pi and other edge devices.
**Business benefit:** Turns a manual counting task into an instant one. It needed only 85 labelled images, thanks to transfer learning, so adapting it to a new product line is cheap and fast. It can also run on low-cost hardware.
**Cost:** Trained on a Colab GPU with free annotation tooling (MakeSense.ai). Deployed on Streamlit Community Cloud.
**Results:** about 0.995 mAP50 on validation.
**Do not claim:** Real-world accuracy beyond that dataset. Validation used only 9 images across 5 classes.

## 3. DFU Ensemble Classifier (medical-image screening)
**Tech:** PyTorch, ResNet18 (5-model ensemble), scikit-learn, Streamlit
**Problem:** Diabetic foot ulcers are serious: per the README, 56% become infected and 20% lead to amputation. Manual wound assessment is slow and inconsistent.
**Solution:** Classifies infection and ischaemia from a single wound photo, maps the result to one of 4 wound types, and shows suggested treatment guidance. I tuned thresholds per task and prioritised recall, because a missed infection is the costly error.
**Business benefit:** Consistent, instant first-pass triage that could help clinicians prioritise urgent cases. Threshold tuning improved results with no retraining.
**Cost:** Runs on CPU with small fp16 weights, so inference needs no GPU.
**Results:** Infection F1 0.855 (recall 0.968, 4 missed of 125). Ischaemia F1 0.824 (recall 0.875, 4 missed of 32).
**Do not claim:** Clinical use or validation. The README states it is an academic proof of concept only.

## 4. Nextcloud Home Server (private cloud storage)
**Tech:** Linux (AntiX), Apache2, PHP, MariaDB, Nextcloud, Tailscale
**Problem:** Commercial cloud storage means ongoing fees and trusting a third party with your files.
**Solution:** A self-hosted Google-Drive-style platform with file sync, web access, user login, and secure remote access over Tailscale.
**Business benefit:** Full control of data and no per-user storage subscription. It was built on a laptop over 10 years old with 2 GB of RAM, so it makes use of hardware that would otherwise be thrown away.
**Cost:** Existing hardware plus open-source software. It currently serves 293 GB of storage, with 11 GB used.
**Skills shown:** Linux administration, networking, DNS troubleshooting, log analysis, debugging real deployment errors (HTTP 500s, missing PHP modules, trusted-domain blocks).
**Do not claim:** Production-grade hosting. HTTPS, automated backups and monitoring are listed as future work.

## 5. Tennis Fusion (e-commerce platform)
**Tech:** .NET 9, ASP.NET Core Web API, Entity Framework Core, Angular 20, SQL Server, Redis, SignalR, Stripe, Docker
**Problem:** A small retailer needs to sell online with search, a cart, secure payment and order tracking, without stitching together separate tools.
**Solution:** A full-stack store with product search, filtering and sorting, a Redis-backed shopping cart that survives sessions, Stripe checkout, user accounts, and live order-status updates pushed to the customer.
**Business benefit:** Covers the whole path from browsing to paid order. Live order status means fewer "where is my order?" support questions. Redis keeps carts so customers don't lose them.
**Cost:** Runs on a Docker-based stack with Stripe's standard payment processing model.
**Do not claim:** A live shop, real customers or revenue. Stripe is in test mode.

## 6. Edge-AI Pest Monitoring Station (agritech IoT)
**Tech:** Raspberry Pi Zero 2 W, Python, OpenCV, TensorFlow Lite, SQLite, Linux, IP66 enclosure
**Problem:** Farm workers walk the rows, inspect sticky traps, count insects and log them by hand. It is slow, error-prone, and delays pesticide decisions.
**Solution:** A field-deployed unit that photographs the trap on a schedule, then detects and counts pests on-device with no cloud connection. It logs the counts with timestamps and power health.
**Business benefit:** Replaces manual scouting with continuous, local pest-density data, so spraying can be targeted instead of applied blanket-style. It works without internet in the field and needs no technician visit to take readings.
**Cost:** Deliberately low-cost parts: a Pi Zero 2 W (about 100 mA idle versus about 600 mA for a Pi 4), a standard 20,000 mAh power bank, and a polycarbonate junction box. No total price is stated in the README.
**Results:** 91.4% mAP on-device. Runs up to 16 days on one power bank charge after I cut idle draw from about 180 mA to under 45 mA. Passed a 48-hour misting-chamber test with no water ingress or fogging.
**Do not claim:** Measured pesticide savings or farm customers. Reducing over-application is the design goal, and the README reports no field figures for it.

## 7. Pyro Protector (autonomous firefighting robot)
**Tech:** Raspberry Pi 4, Python, ESP32 redesign (Arduino C++), IoT (ThingSpeak), sensors, relay-driven pump
**Problem:** Firefighters enter unknown hazardous areas blind, and small fires grow while crews are still arriving.
**Solution:** A robot that patrols an area using Boustrophedon (lawnmower) coverage and obstacle avoidance, detects fire with flame sensors, alerts the user through a cloud dashboard, and suppresses small fires with a servo-aimed water pump. It has a manual pilot mode.
**Business benefit:** Scouts and suppresses before crews arrive, keeping people out of danger and saving critical minutes. Remote dashboard monitoring shows temperature, humidity, flame and water level.
**Cost:** The whole prototype cost RM 361 (Malaysian ringgit) in parts, using used components where possible. The ESP32 redesign targets lower power and a lower price.
**Do not claim:** A deployed or field-tested product. It is a capstone prototype from MMU University with about 1.7 hours of runtime at full load.