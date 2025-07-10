# LINCS-Dams
LINCS Dams is cost-effective prototype for small embankment dam monitoring. The experimental setup uses affordable sensors, including micro-electromechanical system (MEMS) in-place inclinometers (IPIs), water-level gauges, and vibration accelerometers. Sensor outputs are managed by a finite state machine (FSM) that defines accident driven alert and alarm levels while dynamically adjusting each sensor’s data sampling frequency, optimizing energy consumption and ensuring timely responses.

This repository contains the open-source code developed for this system, in addition to all the data gathered in experimental tests. The software developed builds upon previosly created code. The following sections go over the repository organization and the state of the art in dam monitoring.

## Repository Organization
The root of the repository has two folders: Documents and Code. On the Documents folder, you can find the experimental tests' results, in addition to a system installation and troubleshooting guide. The code folder has the software developed for each of the system's components, which includes the LiDAR module, the inclinometer and the state machine script.

### LiDAR Module
The folder /code/lidar/water_module contains the evolution of this module's software. The last version, v3, is the final evolution of this software thus far. The system has fault-tolerance, instruction reception and low-pass filter features. Despite not having the full code available, this software was developed with the help of some code snippets that were made available by the system's creator, Figueiredo (http://hdl.handle.net/10362/165844), on his Master's dissertation document. 
Parts of the LINCS Dams' architecture were also based on the work developed by Figueiredo, namely using a Raspberry Pi to run an MQTT broker and using a state machine to control behaviour. The LINCS Dams system further refined the state machine implementation approach by using a lightweight library and removing third-party services, adopting an on-premises approach instead.

### IPI
The folder /code/ipi/ESP8266_wemosMini contains the code for each of the three microcontroller types that compose this system. ESP0 is the microcontroller that is in each of the inclinometer's nodes. ESP1 and ESP2 are the two ESP8266 boards that comprise the master node of this subsystem. ESP1 is the bridge between ESP0 and ESP2, while ESP2 makes the connection between the IPI and the MQTT broker. The folder /code/ipi/tig-stack contains the docker-compose yaml file and each of the services' configuration and support files.
The code that served as the foundation for this part of the LINCS Dams was developed by Santos and Marcelino (LNEC) and can be found here: https://www.taylorfrancis.com/chapters/oa-edit/10.1201/9781003431749-419/development-laboratory-testing-low-cost-wireless-place-inclinometer-prototype-correia-dos-santos-marcelino. The IPI itself was also lent to the LINCS Dams team, enabling us to focus mostly on software development and test planning.

### State Machine Script
In /code/scripts/state_machine there are the two versions developed for the dynamic behavior implementation based on a finite state machine, using the Pytransitions (https://github.com/pytransitions/transitions) library. Please refer to the paper for a deeper explanation of the states, events, triggers, and overall logic behind the state machine's design.


## State of the Art and Related Work

Santos and Marcelino (https://www.taylorfrancis.com/chapters/oa-edit/10.1201/9781003431749-419/development-laboratory-testing-low-cost-wireless-place-inclinometer-prototype-correia-dos-santos-marcelino) put forward an IPI prototype that is not just a low-cost system but also innovates with collected data being transmitted wirelessly. This project’s main goal was to create an affordable IPI monitoring system that could reliably record embankments’ lateral deformations. The prototype successfully read inclination changes relatively accurately. Wireless communication between components was also 
effectively implemented.

Palma (http://hdl.handle.net/10362/183041) developed a web application for real-time monitoring and visualization of data from In-Place Inclinometers (IPI), more specifically the IPI built by Santos and Marcelino. Efforts were made to create a modern and responsive design, which is a distinguishing factor, compared with most other comercial softwares for this purpose. Palma used up to date technologies such as ReactJS and Recharts to create meaningful visualizations, allowing users to make better decisions based on the data gathered by the IoT system.

Figueiredo (http://hdl.handle.net/10362/165844), as part of his master’s thesis, designed a low-cost IoT system to measure the impact of docking ships on port infrastructures. The system was intended to collect, store, and analyze data, identify maintenance needs, and alert the relevant parties. The final prototype was able to reliably read the impact of vessels docking on a simulated port structure. 

Rohith et al. (https://ieeexplore.ieee.org/document/9243503) created a similar test setup to the one used on this project, in addition to employing similar sensors to the ones used for this paper. They successfully tested the system in this scale dam replica setup, verifying the correct implementation of their smart dam monitoring system.

Teixidó et al. (https://www.mdpi.com/1424-8220/18/11/3817) created a wireless system that detected floods in smart homes.The goal was to develop a solution with which home owners could remotely interact with through the internet. The system’s behavior was implemented using a state machine and it was defined as the following cycle: the system hibernates to save energy, waking up periodically to send basic information or entering the alarm state if a flood was detected, in which case an alert message is sent to the user.

Ho et al. (https://ieeexplore.ieee.org/document/5226920), describe the theoretical implementation of an autonomous home health care system to monitor the glucose levels of users, using a state machine to define the sensor's behaviour. The system would consist of an implantable sensor to measure the users’ glucose levels every minute, a base station and an external network of nodes installed in the user’s home. The implanted sensor would use a state machine to minimize the power consumption.
    
