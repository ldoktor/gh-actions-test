import os
import re
import requests
import time

class Checker:
    def __init__(self):
        required_jobs = os.getenv("REQUIRED_JOBS")
        if required_jobs:
            required_jobs = required_jobs.split(",")
        else:
            required_jobs = []
        required_regexps = os.getenv("REQUIRED_REGEXPS")
        self.required_regexps = []
        if required_regexps:
            for regexp in required_regexps.split(','):
                self.required_regexps.append(re.compile(regexp))
        if not required_jobs and not self.required_regexps:
            raise RuntimeError("No REQUIRED_JOBS or REQUIRED_REGEXPS defined")
        self.results = {job: [] for job in required_jobs}

    def record(self, workflow_id, job):
        job_name = job['name']
        if job_name not in self.results:
            for re_job in self.required_regexps:
                if re_job.match(job_name):
                    self.results[job_name] = []
                    break
            else:
                # Not a required job
                return
        if job_name not in self.results:
            return False
        if job['status'] != 'completed':
            self.results[job_name].append((workflow_id, 'Not Completed'))
            return True
        if job['conclusion'] != 'success':
            self.results[job_name].append((workflow_id, f"Not success ({job['conclusion']})"))
            return False
        self.results[job_name].append((workflow_id, "Passed"))
        return False

    def status(self):
        failed = False
        for job, status in self.results.items():
            if not status:
                return 1
            for stat in status:
                if stat[1] != "Passed":
                    return 1
        return 0

    def get_latest_commit_sha(self, pr_number):
        response = requests.get(
            f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/pulls/{pr_number}/commits",
            headers={"Accept": "application/vnd.github.v3+json"}
        )
        response.raise_for_status()
        commits = response.json()
        return commits[0]['sha'] if commits else None

    def get_jobs_for_workflow_run(self, run_id):
        response = requests.get(
            f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{run_id}/jobs",
            headers={"Accept": "application/vnd.github.v3+json"}
        )
        response.raise_for_status()
        return response.json()['jobs']

    def check_workflow_runs_status(self, pr_number):
        latest_commit_sha = self.get_latest_commit_sha(pr_number)
        if not latest_commit_sha:
            print("Unable to retrieve the latest commit SHA.")
            return False

        response = requests.get(
            f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/actions/runs",
            params={"head_sha": latest_commit_sha},
            headers={"Accept": "application/vnd.github.v3+json"}
        )
        response.raise_for_status()
        workflow_runs = response.json()['workflow_runs']

        for run in workflow_runs:
            workflow_id = run['id']
            jobs = self.get_jobs_for_workflow_run(workflow_id)
            for job in jobs:
                if self.record(workflow_id, job):
                    # TODO: Remove this debug output
                    print(f"Some required workflows are still running {job}")
                    return 127
        print(self)
        return self.status()

    def run(self):
        pr_number = os.getenv("PR_NUMBER")
        while True:
            ret = self.check_workflow_runs_status(pr_number)
            if ret == 127:
                # TODO: Change to 60s
                time.sleep(10)
                continue
            exit(ret)

    def __str__(self):
        out = []
        for job, status in self.results.items():
            if not status:
                out.append(f"FAIL: {job} - No results so far")
                continue
            for stat in status:
                if stat[1] == "Passed":
                    out.append(f"PASS: {job} - {stat[0]}")
                else:
                    out.append(f"FAIL: {job} - {stat[0]} - {stat[1]}")
        out = '\n'.join(sorted(out))
        if self.status():
            return f"{out}\n\nNot all required jobs passed, check the logs!"
        return f"{out}\n\nAll jobs passed"


if __name__ == "__main__":
    Checker().run()

