# Synthetic Provider package

This package is synthetic and contains no user data. It creates one small world,
shows a click counter, and destroys only that world when it exits. It is designed to
exercise Manager preview, unpack, two-step run confirmation, and action receipts.

The package requires Python plus `websockets`; the World Manager never installs
dependencies. Install the example requirements after a separate user confirmation:

```powershell
python -m pip install -r examples/python/requirements.txt
```

Build the `.wcp` archive with `python scripts/build_provider_bundle.py`, then drop the
generated file onto the World Manager. Preview and installation only read and unpack
files. The code runs only after the final explicit confirmation.
