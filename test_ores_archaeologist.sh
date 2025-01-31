#!/bin/bash
source ./bin/activate

python3 ores_archaeologist.py get_all_threshholds ores_bias_data/test_cutoffs.csv --output='ores_bias_data/test_cutoffs_threshholds.csv'

#python3 ores_archaeologist.py score_history data/enwiki_revisions_small_c98ec.csv --output data/enwiki_revisions_small_error.csv

python3 ores_archaeologist.py get_all_thresholds --cutoffs=data/ores_rcfilters_enwiki_cutoffs.csv --output=data/ores_rcfilters_enwiki_thresholds.csv


#python3.6 ores_archaeologist.py get_threshhold --wiki_db=enwiki --date=2018-08-07 --threshhold_string="maximum recall @ precision >= 0.99" # 

#python3.6 ores_archaeologist.py score_wiki_commit_revisions --commit=860c70b73de36d63584db019cccf841f943622e7 --wiki_db=kowiki --all_revisions='ores_bias_data/test_revisions_sample.csv' --load-environment=True --wrap=True

# python3.6 ores_archaeologist.py score_commit_revisions --commit=860c70b73de36d63584db019cccf841f943622e7 --cutoff_revisions='ores_bias_data/test_revisions_sample.csv'  --wrap=True --load_environment=True

#python3.6 ores_archaeologist.py score_history --cutoff_revisions='ores_bias_data/test_revisions_sample2.csv'  --wrap=True

#python3.6 ores_archaeologist.py score_revisions --wiki_db=enwiki --uri=https://en.wikipedia.org --date=2018-08-22 --infile='ores_bias_data/test_revisions_sample2.csv'
