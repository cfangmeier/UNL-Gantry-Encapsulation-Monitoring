#!/usr/bin/env bash


function archive {
    prefix="/home/dominguez/cfangmeier/elog_git/logbooks/SiLab_Logbook/*/"
    command="zip -uj $2 $prefix$3"
    echo $command
    ssh $1@t3.unl.edu $command
    scp $1@t3.unl.edu:~/$2 .
}


function to_txt {
    mkdir docs
    unzip Gluing_Logs.zip  -d docs
    cd docs
    echo "Converting docs to txt, give it a minute..."
    libreoffice --convert-to txt *.doc > /dev/null
    echo "Finished"
    cd ..
    rm Gluing_Logs.zip
    zip -uj Gluing_Logs.zip docs/*.txt
    rm -rf docs
}

if [ "$#" -eq 1 ]; then
    echo "Potting logs"
    # make archive and copy files over
    archive $1 "Potting_Logs.zip" "*_Config-*-*-*.zip"
    archive $1 "Gluing_Logs.zip" "*glueing_report__*-*-*_*_*.doc"
    to_txt
fi


./Logs2JSON.py Potting_Logs.zip Gluing_Logs.zip
if [ $? -eq 0 ]
then
    echo "Finished creating JSON file for potting data"
    exit 0
else
    echo "Error parsing Logfiles"
    exit 1
fi
