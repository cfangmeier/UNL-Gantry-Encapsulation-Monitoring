#!/usr/bin/env bash

# ssh $1@t3.unl.edu "zip -uj Potting_Logs.zip /home/dominguez/cfangmeier/elog_git/logbooks/SiLab_Logbook/*/*_Config-*-*-*.zip"
scp $1@t3.unl.edu:~/Potting_Logs.zip .
./PottingLog2JSON.py Potting_Logs.zip
if [ $? -eq 0 ]
then
    echo "Finished creating JSON file for potting data"
else
    echo "Error parsing Logfiles"
fi
