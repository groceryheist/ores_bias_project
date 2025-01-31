# functions in this file can be run under any environment.
# this essentially means no pandas
import time
import subprocess
import dateutil
import mwapi
from sortedcontainers import SortedDict
import sys
import datetime
import git
import re
import os
import pickle
import fire
import json
from project_settings import *

def dedup_chronological(df, distinct_cols, direction='forward'):
    df = df.sort_values(['wiki_db','date'])
    bywiki = df.groupby('wiki_db')[distinct_cols]
    # d.shift(1) == d if the previous entry is the same as the current entry
    if direction == 'forward':
        identical = bywiki.apply(lambda d: ((d.shift(1) == d) | (d.shift(1).isna() & d.isna()))).all(1)
    else:
        identical = bywiki.apply(lambda d: ((d.shift(-1) == d) | (d.shift(-1).isna() & d.isna()))).all(1)
    return (df[~identical])
                                

# python 3.5 doesn't have datetime.fromisoformat
call_log = "syscalls.sh"
from dateutil import parser
fromisoformat = parser.isoparse

api = mwapi.Session("https://en.wikipedia.org",'ores bias project by groceryheist <nathante@uw.edu>')

sys.path.append("../../mw_revert_tool_detector")

siteList = pickle.load(open("data/wikimedia_sites.pickle",'rb'))

tmpdir = os.path.join(os.path.abspath('.'),'tmp')

if not os.path.exists(tmpdir):
    os.mkdir(tmpdir)

os.environ['TMPDIR'] = os.path.join(os.path.abspath('.'),'tmp')
repo_path = "../mediawiki-services-ores-deploy/"
editquality_repo_path = '../editquality_groceryheist'
wheels_repo_path = '../wheels'

date_commits = SortedDict()
wiki_date_commits = {}

editquality_commits = {}
wheels_commits = {}
    
repo = git.Repo(repo_path)
repo.git.checkout("-f", 'master')
repo.git.pull()
editquality_repo = git.Repo(editquality_repo_path)
editquality_repo.git.checkout("-f", 'master')
editquality_repo.git.pull()
wheels_repo = git.Repo(wheels_repo_path)
wheels_repo.git.checkout("-f", 'master')
wheels_repo.git.pull()
commits = repo.iter_commits(paths=["submodules/editquality"])

wheels_commits_path = os.path.join(data_dir,"wheels_commits.pickle")
editquality_commits_path = os.path.join(data_dir,"editquality_commits.pickle")
date_commits_path = os.path.join(data_dir, "date_commits.pickle")
wiki_date_commits_path = os.path.join(data_dir, "wiki_date_commits.pickle")
lfs_transition_date = fromisoformat("2018-08-10")

if os.path.exists(wiki_date_commits_path) and os.path.exists(date_commits_path):
    wiki_date_commits = pickle.load(open(wiki_date_commits_path,'rb'))
    date_commits = pickle.load(open(date_commits_path,'rb'))
    editquality_commits = pickle.load(open(editquality_commits_path,'rb'))
    wheels_commits = pickle.load(open(wheels_commits_path,'rb'))
else:
    for commit in commits:
        editquality_repo.git.checkout('-f', 'master')
        wheels_repo.git.checkout('-f', 'master')
        repo.git.checkout('-f', commit)
        commit_datetime = datetime.datetime.fromtimestamp(commit.committed_datetime.timestamp())
        if commit_datetime > lfs_transition_date:
            models_path = os.path.join(repo_path,'submodules/editquality/models')

            try:
                editquality_submodule = repo.submodule("submodules/editquality")
                if hasattr(editquality_submodule,'update'): 
                    editquality_submodule.update(init=True, force=True, recursive=True)
            except Exception as e:
                print(commit_datetime)
                print(e)

        # find the most recent commit in the editquality repo
        else:
            models_path = os.path.join(editquality_repo_path,'models')
            editquality_commit = next(editquality_repo.iter_commits(until=commit_datetime, max_count=1))
            editquality_commits[commit.hexsha] = editquality_commit.hexsha
            editquality_repo.git.checkout('-f', editquality_commit)
            time.sleep(5)
            # reset to master

        found_prior_commit = False
        found_next_commit = False
        try:

            wheels_commit = next(wheels_repo.iter_commits(until=commit_datetime, max_count=1))

            wheels_commit_time = datetime.datetime.fromtimestamp(wheels_commit.committed_datetime.timestamp())
            wheels_time_diff = commit_datetime - wheels_commit_time
            print("time from wheels commit {0} to deploy:{1}".format(wheels_commit.hexsha[0:10], wheels_time_diff))
            found_prior_commit = True

        except StopIteration as e:
            pass

        try:
            wheels_commit2 = next(wheels_repo.iter_commits(since=commit_datetime, max_count=1))
            wheels_commit_time2 = datetime.datetime.fromtimestamp(wheels_commit2.committed_datetime.timestamp())
            wheels_time_diff2 = wheels_commit_time2 - commit_datetime

            print("time from deploy to wheels commit {0}:{1}".format(wheels_commit2.hexsha[0:10], wheels_time_diff2))
            found_next_commit = True
        except StopIteration as e:
            pass
        

        if found_prior_commit and found_next_commit:
            if wheels_time_diff2 <= datetime.timedelta(days=1):
                use_commit = wheels_commit2.hexsha
            else:
                use_commit = wheels_commit.hexsha


        elif found_next_commit:
            use_commit = wheels_commit2.hexsha
        else:
            print("found no wheels commit for commit {0} at {1}".format(commit, commit_datetime))
            
        wheels_commits[commit.hexsha] = use_commit
        print("using commit {0}".format(use_commit))

        date_commits[commit_datetime] = commit.hexsha
        model_re = re.compile(r'(.*)\.damaging\..*\.model')
        files = os.listdir(models_path)

        for f in files:
            wiki_db = model_re.findall(f)
            if len(wiki_db) > 0:
                d = wiki_date_commits.get(wiki_db[0], SortedDict())
                d[commit_datetime] = commit.hexsha
                wiki_date_commits[wiki_db[0]] = d


    pickle.dump(wheels_commits, open(wheels_commits_path,'wb'))
    pickle.dump(wiki_date_commits, open(wiki_date_commits_path,'wb'))
    pickle.dump(date_commits, open(date_commits_path,'wb'))
    pickle.dump(editquality_commits, open(editquality_commits_path,'wb'))

wiki_date_commits['simplewiki'] = wiki_date_commits['enwiki']
repo.git.checkout("-f", "master")
editquality_repo.git.checkout('-f', "master")
wheels_repo.git.checkout("-f", "master")

def lookup_commit_from_wiki_date(wiki_db, date):
    return lookup_commit_from_date(date, wiki_date_commits[wiki_db])

def lookup_commit_from_date(date, sorted_dict):
    if isinstance(date, str):
        date = fromisoformat(date)

    idx = sorted_dict.bisect_right(date)

    if idx > 0:
        idx = idx - 1
    commited_datetime = sorted_dict.keys()[idx]
    commit = sorted_dict[commited_datetime]

    return commit

def find_model_file(wiki_db, commit, model_type='damaging'):
    
    if commit in editquality_commits:
        models_path = os.path.join(editquality_repo_path, 'models')
    else:
        models_path = os.path.join(repo_path, 'submodules/editquality/models')
    
    if wiki_db == 'simplewiki':
        wiki_db = 'enwiki'
    model_re = r'{0}\.{1}\..*\.model'.format(wiki_db, model_type)
    files = os.listdir(models_path)
    model_files = [f for f in files if re.match(model_re, f)]
    if len(model_files) > 0:
        return os.path.join(models_path, model_files[0])

def get_wheels_package_versions(path):
    name_version_re = re.compile(r"(.*?)-(.*?)-.*.whl")
    files = os.listdir(path)
    matches = [name_version_re.findall(f) for f in files]
    for matchlist in matches:
        if len(matchlist) > 0:
            match = matchlist[0]
            if len(match) == 2:
                yield (match[0],match[1])

# load the environment according to the deploy
def load_model_environment(date = None, commit=None, wiki_db=None):
    
    # we'll need to see what's installed so we can remove unnecessary packages at each step to avoid conflicts.

    subprocess.run("source {0}/bin/activate && python3 -m pip freeze > old_requirements.txt".format(repo.working_dir), shell=True, executable='/bin/bash')

    old_versions = {name:version for name, version in [(s[0], s[1]) for s in [l.split('==') for l in open('old_requirements.txt','r')]]}

    if isinstance(date, str):
        date = fromisoformat(date)

    if commit is None and (wiki_db is None or date is None):
        raise ValueError("Commit or (Wiki_db and date) required to load environment")

    if commit is None:
        commit = lookup_commit_from_wiki_date(date, wiki_db)

    print("date:{0}, commit:{1}".format(date, commit))

    repo.git.checkout('-f', commit)
    
    curdir = os.path.abspath(".")
    os.chdir(repo_path)
    subprocess.run("git submodule sync --recursive",shell=True)
    os.chdir(curdir)

    print("loading editquality")
    if commit in editquality_commits:

        print('checkout {0} from {1}'.format(editquality_commits[commit], editquality_repo.working_dir))
        editquality_repo.git.checkout('-f', 'master')
        editquality_repo.git.checkout('-f', editquality_commits[commit])
        editquality_repo.git.submodule("sync","--recursive")
        editquality_path = editquality_repo_path
    else:
        editquality_path = os.path.join(repo.working_dir,"submodules/editquality")
        try: 
            editquality_submodule = repo.submodule("submodules/editquality")            
            editquality_submodule.update(init=True, recursive=True, force=True)

        except git.exc.GitCommandError as e:
            print(e)

        except AttributeError as e:
            print(e)

    print("loading wheels")
    wheels_path = wheels_repo.working_dir
    if commit in wheels_commits:
        print("updating wheels to {0}".format(wheels_commits[commit]))
        wheels_repo.git.checkout("-f", wheels_commits[commit])
        wheels_repo.git.submodule("sync","--recursive")

    else:
        print("loading wheels submodule")
        wheels_path = os.path.join(repo.working_dir,"submodules/wheels")
        try:
            wheels_submodule = repo.submodule("submodules/wheels")
            wheels_submodule.update(init=True, recursive=True, force=True)

        except git.exc.GitCommandError as e:
            print(e)

    # the order of dependency priorities: wheels > repo > editquality_repo
    wheels_package_versions = dict(get_wheels_package_versions(wheels_path))
    
    if os.path.exists(os.path.join(repo_path,'frozen-requirements.txt')):
        repo_package_versions = {s[0]:s[1] for s in [l.strip().replace("-","_").split('==') for l in open(os.path.join(repo.working_dir,'frozen-requirements.txt'))]}
    else:
        repo_package_versions = {}

    #     reqtxt = []

    # elif os.path.exists(os.path.join(repo_path,'requirements.txt')):
    #     reqtxt = open(os.path.join(repo.working_dir,'requirements.txt')).readlines()
    #     repo_package_versions = {}

    packages = {**repo_package_versions, **wheels_package_versions}

    if packages.get('pywikibase',None) == '0.0.4a':
        packages['pywikibase'] = '0.0.4'

    no_install = {'pkg_resources','numpy'}
    requirements = ["{0}=={1}\n".format(name, version) for name, version in packages.items() if name not in no_install]
    # requirements = requirements + reqtxt 

    ## special case pywikibase 0.0.4a

    with open("temp_requirements.txt",'w') as reqfile:
         reqfile.writelines(requirements)
         reqfile.writelines("numpy==1.17.0")

    # modules that are safe and good to keep since they are either required or have long compilation times. 
    to_keep = ['fire','python-dateutil','pkg_resources','pkg-resources','sortedcontainers','python-git','gitpython','gitdb2','pandas','send2trash','smmap2','termcolor','mwapi','urllib3','certifi','chardet','idna','mysqltsv','more-itertools', 'editquality','numpy','mwcomments']


    to_uninstall = [k + '\n' for k in old_versions.keys() if k not in packages and k.lower() not in to_keep]
    with open('to_uninstall.txt','w') as uf:
        uf.writelines(to_uninstall)
        
    call = "source {0}/bin/activate".format(repo.working_dir)
    
    if len(to_uninstall) > 0:
        call = call + " && python3 -m pip uninstall -y -r to_uninstall.txt"    

    call = call + " && python3 -m pip download -r temp_requirements.txt -d deps && python3 -m pip install -r temp_requirements.txt --find-links=deps --no-deps"

    print(editquality_path)
    call = call + " && cd {0} && python3 setup.py install && cd ../ores_bias_project/ && source ./bin/activate".format(editquality_path)

    with open(call_log,'a') as log:
        log.write(call + '\n')
    proc = subprocess.run(call, shell=True, executable="/bin/bash")

def set_revscoring_version(model_file, commit):
    from packaging import version
    from revscoring import __version__

    proc = subprocess.run("source ../mediawiki-services-ores-deploy/bin/activate && python3 -m pip show revscoring", shell=True, stdout=subprocess.PIPE, executable='/bin/bash', universal_newlines=True)

    res = proc.stdout
    revscoring_re = re.compile("Version: (.*)")
    revscoring_version = revscoring_re.findall(res)[0]
    revscoring_version = version.parse(revscoring_version) 
    if revscoring_version < version.parse("2.0.3"):
        call = "source ../mediawiki-services-ores-deploy/bin/activate && revscoring model_info {0} --as-json".format(model_file)

    #special case for zhwiki
     # elif ('zhwiki' in model_file):
     #    subprocess.run("source ../mediawiki-services-ores-deploy/bin/activate && python3 -m pip install revscoring==2.2.0 numpy==1.17.0", shell=True, stdout=subprocess.PIPE, executable="/bin/bash", universal_newlines=True)

    #special case for arwiki
    elif commit.startswith("47d9a6bad2") and ('arwiki' in model_file or 'lvwiki' in model_file):
        subprocess.run("source ../mediawiki-services-ores-deploy/bin/activate && python3 -m pip install revscoring==2.2.0 numpy==1.17.0", shell=True, stdout=subprocess.PIPE, executable="/bin/bash", universal_newlines=True)
        return
    else:
        call = "source ../mediawiki-services-ores-deploy/bin/activate && revscoring model_info {0} --formatting=json".format(model_file)


    # if 'lvwiki' in model_file:
    # if revscoring version is older than # Aug 12, 2017  commit cc42736f3a934b1dca0cda8d74817feeda773747 pass --as-json
    # other wise pass --formatting=json
    # we might need to special case lvwiki

    try:
        proc = subprocess.run(call, shell=True, executable="/bin/bash", stdout=subprocess.PIPE, universal_newlines=True)
        res = json.loads(proc.stdout)
        version = res.get("environment",{}).get("revscoring_version",None)
    except Exception as e:
        print(e)
        print(model_file)
        version = None

    if version is not None:
        subprocess.run("source ../mediawiki-services-ores-deploy/bin/activate && python3 -m pip install revscoring=={0} numpy==1.17.0".format(version), shell=True, executable="/bin/bash")
