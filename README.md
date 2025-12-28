# Cost Explorer
Compare AWS costs between weeks

## Usage
Assume an AWS role with access to cost explorer, then:
```bash
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt

python main.py

## or
python main.py --end-date 2025-12-20
```
