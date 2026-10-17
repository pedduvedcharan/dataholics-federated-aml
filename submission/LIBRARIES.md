# Open-source software and data used (for the submission form)

All project code in `fedaml/` and `scripts/` was written by team Dataholics during the IBM Z Datathon 2026 (Oct 17–18).

| Name | Version seen on the VM | Use | License | Link |
|---|---|---|---|---|
| Ubuntu | 24.04.5 LTS (s390x) | host OS and container base | various | https://ubuntu.com |
| Docker Engine / Docker Compose | 29.1.3 / 2.40.3 | sandboxed containers, orchestration | Apache-2.0 | https://docs.docker.com |
| Python | 3.12.3 | everything | PSF | https://www.python.org |
| NumPy | 1.26.4 | numerics | BSD-3 | https://numpy.org |
| SciPy | 1.11.4 | L-BFGS in the FedProx-style trainer | BSD-3 | https://scipy.org |
| pandas | 2.1.4 | data partition and features | BSD-3 | https://pandas.pydata.org |
| scikit-learn | 1.4.1 | logistic regression, random forest, HistGradientBoosting, metrics, class weights | BSD-3 | https://scikit-learn.org |
| Flask | 3.0.2 | coordinator API, dashboard | BSD-3 | https://flask.palletsprojects.com |
| requests | 2.31.0 | bank → coordinator HTTP (inside the egress function) | Apache-2.0 | https://requests.readthedocs.io |
| matplotlib | 3.6.3 | figures | PSF-based | https://matplotlib.org |
| Chart.js | CDN | dashboard charts, in the browser | MIT | https://www.chartjs.org |
| IBM Adversarial Robustness Toolbox (ART) | 1.20.1 | black-box membership-inference variant (footnote attack) | MIT | https://github.com/Trusted-AI/adversarial-robustness-toolbox |
| python-paillier (`phe`) | 1.5.0 | Paillier homomorphic encryption (stretch, not in the demo) | GPL-3.0 | https://github.com/data61/python-paillier |
| dilithium-py | installed | ML-DSA post-quantum signatures (stretch, not in the demo) | MIT | https://github.com/GiacomoPope/dilithium-py |
| llama.cpp | built from source on s390x | CPU LLM runtime (`llama-server`), big-endian GGUF conversion script | MIT | https://github.com/ggml-org/llama.cpp |
| Qwen2.5-0.5B-Instruct-GGUF, Qwen2.5-1.5B-Instruct-GGUF | Q8_0, converted to big-endian | SAR assessment paragraph | Apache-2.0 | https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF · https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF |

Dataset: IBM Transactions for Anti Money Laundering (AML), HI-Small (`HI-Small_Trans.csv`), synthetic, public on Kaggle: https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml. Not stored in the repository.

Methods referenced: FedAvg (McMahan et al. 2017), FedProx (Li et al. 2020), Gaussian mechanism for DP, membership-inference auditing (Jagielski et al. 2020; Nasr et al. 2021), loss-threshold membership inference (Yeom et al. 2018).
