# Automated Edge-AI Pest Monitoring Station: An Agritech Case Study

## Project Overview

In modern agriculture, Integrated Pest Management (IPM) relies heavily on the accurate tracking of insect populations to determine when and where to apply targeted pesticides. Traditionally, this requires farm workers to manually walk rows of crops, inspect physical sticky traps, count insects, and log data by hand. This process is slow, labor-intensive, prone to human error, and delays critical intervention.

  

During my engineering internship, I designed and developed an **Automated Edge-AI Pest Monitoring Station**. Deployed directly into an active farming field, this outdoor IoT unit autonomously captures scheduled, high-resolution imagery of a flat sticky pest trap and processes the images locally at the edge to detect, classify, and count pests in real-time. By automating this workflow, the system provides farmers with immediate, localized pest-density telemetry, reducing pesticide over-application and preventing localized infestations before they spread.

  

## Objectives

- **Autonomous Edge Inference:** Execute lightweight computer vision models directly on a field-deployed microcontroller or single-board computer without relying on constant cloud connectivity.
    
      
    
- **Robust Environmental Resilience:** Design a low-cost, water-resistant housing rated to survive heavy, continuous rainfall and high humidity levels without fogging the camera optics.
    
      
    
- **Power-Optimized Lifespan:** Engineer a hardware and software routine capable of operating remotely on a standard commercial power bank for extended deployment windows.
    
      
    
- **High-Fidelity Telemetry:** Capture crisp, flat-plane images of a standardized yellow sticky card at a height optimized for natural agricultural pest movement.
    
      
    

## Hardware Architecture

Deploying electronics into a damp, unstable agricultural environment required deliberate hardware constraints to balance power draw, computational throughput, and cost.

  

|**Component**|**Selected Hardware**|**Engineering Justification & Constraints**|
|---|---|---|
|**Main Compute**|Raspberry Pi Zero 2 W|Selected over a standard Raspberry Pi 4/5 because it draws significantly less idle power ($\approx 100\text{ mA}$ vs $\approx 600\text{ mA}$) and features a highly compact footprint. Its quad-core 64-bit ARM processor provides just enough computational headroom to run optimized MobileNet edge-inference models.|
|**Imaging Unit**|Raspberry Pi Camera Module 2|Offers a native 8MP resolution, which is more than sufficient for capturing granular insect features at close range. Its native compatibility with the `libcamera` stack allowed for granular programmatic control over exposure and focus.|
|**Power Storage**|20,000mAh Power Bank (with pass-through support)|Acts as the primary power cell. A crucial constraint was ensuring the power bank supported true pass-through charging (simultaneous charging and discharging) so that future solar integrations wouldn't drop power to the Pi during shifting light conditions.|
|**Enclosure**|IP66-Rated Polycarbonate Junction Box|Provides a completely dust-tight seal and protection against powerful water jets from heavy rain. The clear bottom window was modified with outdoor-grade silicone to house the camera lens.|

### Structural Constraints & Form Factor

Initial prototypes positioned the camera close to the ground, but field conditions (mud splashes, tall weeds obscuring natural light, and tractor paths) necessitated an elevated frame. The final platform design mounts the main computing box and flat trap plate at **human shoulder level**. This high-clearance design:

  

1. Prevents mud and debris from splashing onto the camera's optical window during intense downpours.
    
      
    
2. Catches flying pests migrating through the upper crop canopy rather than ground crawlers.
    
      
    
3. Allows easy, ergonomic access for a technician to swap out the flat sticky card without kneeling in the dirt.
    
      
    

## Software Stack / Technologies

- **Linux (Debian / Raspberry Pi OS Lite):** Chosen to eliminate the overhead of a graphical user interface (GUI). Operating entirely via the headless CLI saved precious RAM and minimized baseline CPU power utilization.
    
      
    
- **Python 3.9:** The core application runtime environment. Python was selected due to its mature ecosystem of hardware interaction libraries (`RPi.GPIO`) and first-party bindings for machine learning frameworks.
    
      
    
- **OpenCV (Open Source Computer Vision Library):** Used extensively for pre-processing images—specifically for cropping the frame to the boundaries of the yellow sticky trap, normalizing contrast against fluctuating outdoor sunlight, and isolating contours.
    
      
    
- **TensorFlow Lite:** The inference engine used to deploy our quantized pest-detection model. Standard TensorFlow was too resource-intensive for the Pi Zero's 512MB of RAM; TF Lite reduced our model footprint by nearly 75% while maintaining an acceptable accuracy trade-off.
    
      
    

## System Architecture

```
+-------------------------------------------------------------+
|                     Field Hardware Station                  |
|                                                             |
|   +-------------------+         +-----------------------+   |
|   |  Sticky Pest Trap |         |   Power Bank Unit     |   |
|   +---------+---------+         +-----------+-----------+   |
|             | (Physical Capture)            | (5V DC Power) |
|             ▼                               ▼               |
|   +-----------------------------------------------------+   |
|   |               Raspberry Pi Zero 2 W                 |   |
|   |                                                     |   |
|   |  +---------------------+     +-------------------+  |   |
|   |  |   libcamera Stack   |---->| OpenCV Pipeline   |  |   |
|   |  +---------------------+     +---------+---------+  |   |
|   |                                        |            |   |
|   |                                        ▼            |   |
|   |                              +-------------------+  |   |
|   |                              |  TF Lite Engine   |  |   |
|   |                              +---------+---------+  |   |
|   +----------------------------------------|------------+   |
+--------------------------------------------|----------------+
                                             ▼
                               +---------------------------+
                               | SQLite / Local Data Logs  |
                               +---------------------------+
```

### Communication Flow

1. **Trigger:** A cron job initiates the software routine at scheduled intervals throughout the day.
    
      
    
2. **Capture:** The `libcamera` API drives the Camera Module to pull a raw frame into volatile memory.
    
      
    
3. **Transformation:** OpenCV processes the raw frame to correct lens distortion, isolate the yellow plate, and save an optimized image.
    
      
    
4. **Inference:** The processed image array is fed into the TensorFlow Lite interpreter to evaluate bounding boxes around detected insects.
    
      
    
5. **Storage:** The localized integer count, system timestamp, and power health metric are written directly to a local, lightweight SQLite database file optimized for low disk-write overhead.
    
      
    

## Project Implementation

### Phase 1: Environment Setup and Native Compilation

Because the Raspberry Pi Zero 2 W has constrained memory resources, compiling heavy computer vision libraries directly on the device is incredibly slow and can cause out-of-memory errors. I configured a headless setup using the minimal Debian image and orchestrated dependencies carefully.

  

Bash

```
# Update the core package manager
sudo apt-get update && sudo apt-get upgrade -y

# Install essential system dependencies for image processing and libcamera
sudo apt-get install -y libcamera-dev libjpeg-dev libtiff5-dev libpng-dev \
libavcodec-dev libavformat-dev libswscale-dev libv4l-dev \
libxvidcore-dev libx264-dev libatlas-base-dev gfortran Python3-dev

# Install Python package management tools and runtime dependencies
pip3 install --upgrade pip
pip3 install opencv-python-headless tflite-runtime
```

_Note: Depending on your specific Linux distribution or version of Raspberry Pi OS, package names like `libatlas-base-dev` can vary; ensure your package manager index is fully updated._

  

### Phase 2: The Core OpenCV and Inference Pipeline

The script captures an image, isolates the region of interest (the yellow trap), and applies localized object detection. Below is a simplified representation of the pipeline script (`monitor.py`) I engineered for this system:

  

Python

```
import time
import cv2
import numpy as np
import tflite_runtime.interpreter as tflite

def preprocess_image(image_path, target_size=(300, 300)):
    # Load image using headless openCV
    img = cv2.imread(image_path)
    
    # Convert BGR to HSV color space to easily isolate the yellow sticky trap
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lower_yellow = np.array([15, 100, 100])
    upper_yellow = np.array([30, 255, 255])
    
    # Create mask and find bounding contours of the trap tray
    mask = cv2.inRange(hsv, lower_yellow, upper_yellow)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if contours:
        # Isolate the largest yellow rectangular contour found
        largest_contour = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(largest_contour)
        cropped = img[y:y+h, x:x+w]
    else:
        cropped = img # Fallback to original frame if mask fails due to extreme shade

    # Resize image to match the precise input expected by the TFLite model
    resized = cv2.resize(cropped, target_size)
    input_data = np.expand_dims(resized, axis=0).astype(np.float32)
    return input_data / 255.0  # Normalize pixel values to [0.0, 1.0]

def run_inference(model_path, input_data):
    # Initialize the lightweight TensorFlow Lite Interpreter
    interpreter = tflite.Interpreter(model_path=model_path)
    interpreter.allocate_tensors()
    
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()
    
    # Bind the processed frame to the input tensor slot
    interpreter.set_tensor(input_details[0]['index'], input_data)
    interpreter.invoke()
    
    # Extract prediction boxes and score maps
    output_data = interpreter.get_tensor(output_details[0]['index'])
    return output_data

if __name__ == "__main__":
    # Standardized operational invocation execution loop
    print("[INFO] Starting pipeline execution sequence...")
    processed_frame = preprocess_image("capture.jpg")
    results = run_inference("models/pest_detector_quant.tflite", processed_frame)
    print(f"[INFO] Pipeline complete. Detections payload parsed: {len(results)}")
```

## Configuration

### Linux Automation & Cron Scheduling

To conserve power bank capacity, the device was configured to run on a strict cron interval rather than a continuous loop. The system wakes its processing pipeline once every hour between 6:00 AM and 6:00 PM.

  

To configure the persistent cron task:

  

Bash

```
crontab -e
```

Add the following line to the configuration file to run the script at the top of every hour during daylight hours:

  

Plaintext

```
0 6-18 * * * /usr/bin/python3 /home/pi/pest_monitor/monitor.py >> /home/pi/pest_monitor/execution.log 2>&1
```

### Camera Permission Configuration

By default, access to hardware video devices requires elevated security contexts. The runtime user account must be explicitly added to the video system access group to ensure headless execution doesn't throw permission denials:

  

Bash

```
sudo usermod -a -G video pi
```

## Challenges Encountered

### 1. Optical Lens Fogging and Moisture Capture

- **Problem:** During heavy afternoon rainstorms, the interior of the clear camera window fogged up completely, rendering the image processing pipeline useless due to blurred, non-segmentable frames.
    
      
    
- **Root Cause:** The Raspberry Pi Zero generates localized internal ambient heat inside a completely sealed IP66 enclosure. When cold rain hit the exterior enclosure shell, it caused sudden temperature drops on the surface of the polycarbonate, which condensed the internal humidity directly onto the inside lens window.
    
      
    
- **Investigation:** Inspecting historical execution logs showed that image classification accuracy dropped to 0% during precipitation events, with OpenCV contour detection failing to map the boundaries of the yellow trap.
    
      
    
- **Solution:** I modified the enclosure by cutting a small vent port and installing a **hydrophobic, breathable ePTFE membrane vent cap (Gore Vent)**. This allowed internal air pressure and humidity to normalize with the outside environment while keeping liquid water out. Additionally, I added a small custom 3D-printed sun/rain hood over the external window to keep raindrops from sliding across the lens pane.
    
      
    

### 2. High Battery Drain and Sudden Power Dropouts

- **Problem:** The system would deplete the 20,000mAh power bank within approximately 3 days of standalone continuous deployment, which was far too short for real-world agricultural utility.
    
      
    
- **Root Cause:** The default Linux installation kept the Wi-Fi card, HDMI controller chip, and all four CPU cores powered on at maximum performance scaling loops, consuming power continuously even when no code was executing.
    
      
    
- **Investigation:** Using an inline USB hardware multimeter, I measured a constant current draw of $\approx 180\text{ mA}$ at idle.
    
      
    
- **Solution:** I optimized the system down to an ultra-low power footprint by disabling unneeded hardware interfaces directly in `/boot/config.txt`:
    
      
    

Plaintext

```
# Disable HDMI output to save power
hdmi_blanking=2
dtoverlay=disable-bt

# Underclock the processor during low-demand windows
arm_freq=800
gpu_freq=250
```

Additionally, I explicitly added commands inside the core execution script to turn off the Wi-Fi radio interface transceiver at the end of every active cycle and wake it up only during data transmission windows:

  

Bash

```
sudo rfkill block wifi
```

This brought the idle current draw down to less than **$45\text{ mA}$**, extending the standalone power bank deployment capability to over two weeks of continuous autonomous monitoring.

  

## Testing and Verification

To verify the accuracy and stability of the system prior to true field deployment, I established a rigorous end-to-end evaluation methodology.

  

### Functional Vision Testing

I compiled a test verification dataset containing 150 pre-labeled reference images of sticky pest cards under different lighting profiles (bright direct sun, overcast skies, and deep shadow canopies). A validation script fed these images through the OpenCV segmentation and TF Lite pipeline to compare local inferences with manual annotations.

  

Bash

```
# Execute verification scripts against local golden image samples
python3 tests/verify_pipeline.py --dataset=tests/fixtures/goldens/
```

### Environmental Stress Testing

The complete enclosure unit was mounted inside an artificial misting chamber for 48 hours to simulate severe, multi-day torrential rain conditions. The system recorded continuous internal telemetry regarding relative humidity and temperature to confirm the ePTFE membrane vent functioned correctly. No water ingress or internal condensation occurred.

  

## Final Result

The completed Automated Edge-AI Pest Monitoring Station successfully delivers a field-ready agritech utility.

  

### Key Capabilities

- **Autonomous Multi-Day Lifecycle:** Operates for up to 16 days on a single commercial power bank charge via severe kernel-level power minimization tuning.
    
      
    
- **Edge Inference Accuracy:** Achieved a **$91.4\%$ mean Average Precision (mAP)** locally on-device for identifying major crop-damaging target insects under varying outdoor illumination thresholds.
    
      
    
- **Physical Resilience:** The high shoulder-level stand effectively eliminated mud blinding, and the IP66 modification successfully navigated heavy downpours without fogging issues.
    
      
    
- **Actionable Logging:** Generates clean, structured database records detailing daily infestation vectors, allowing farmers to replace traditional, manual data-logging workflows entirely.
    
      
    

## Skills Demonstrated

- **Embedded Systems Design:** Working with resource-constrained computing platforms, custom I/O handling, and physical peripheral integration.
    
      
    
- **Computer Vision & Edge AI:** Image color-space manipulation (HSV filtering), contour tracking, bounding box extraction, and runtime execution of quantized TensorFlow Lite models.
    
      
    
- **Linux Systems Administration:** Custom kernel configuration tweaks, explicit power management optimization (`rfkill`), and headless cron orchestration.
    
      
    
- **Hardware Engineering & Prototyping:** Designing weatherproofing schemas (IP ratings, hydrophobic membranes) and understanding structural trade-offs for deploying field electronics.
    
      
    

## Future Improvements

- **Deep Sleep Hardware Integration:** Incorporate a low-power hardware real-time clock (RTC) power-shim (like a PiJuice or Witty Pi) to completely cut power to the Raspberry Pi, turning it on only for 3 minutes every hour. This would extend battery life from 16 days to over **6 months**.
    
      
    
- **LoRaWAN Telemetry Link:** Integrate a low-power, long-range LoRa module to transmit the local scalar pest counts back to a central farm base station automatically, removing the need to store data locally or rely on high-power Wi-Fi loops.
    
      
    
- **On-Chip Model Retraining:** Implement a semi-automated pipeline that flags low-confidence image arrays locally and saves them to an SD card partition so that field engineers can use them to retrain and improve the detection model over successive crop seasons.