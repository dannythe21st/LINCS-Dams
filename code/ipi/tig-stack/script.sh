#!/bin/bash
set -e

influx bucket create \
        --name inputs --org ${DOCKER_INFLUXDB_INIT_ORG} # valores de ângulo imposto

#inserir isto no CLI no bash do Docker
#
#influx write -b inputs -o lnec-ascendi "calib1F,inc=inc1,position=Front angle=2,dist=31.2,reading=14521"

#influx bucket create \
#        --name results --org ${DOCKER_INFLUXDB_INIT_ORG} # para colocar o calculo dos cumulativos

#influx task create \
#        --org ${DOCKER_INFLUXDB_INIT_ORG} \  # task para calcular os cumulativos e enviar para "results"
#        -f /etc/tasks/disp_results_task.flux