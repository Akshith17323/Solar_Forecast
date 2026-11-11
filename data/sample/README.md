# Sample data — synthetic fixtures only

Every value in this folder is hand-written, synthetic demonstration/test data.
It does **not** describe a real plant, location, API response or observed weather.
The arbitrary generation numbers have **no established physical unit**.

- `solar_history.csv`: historical-mode schema example, including the candidate target.
- `solar_future.csv`: inference-mode example, without any future target values.
- `forecast_request.json`: HTTP request example; default server returns `model_not_configured`.
- `general_tabular.csv`: example for `config/general.example.yaml`.

Do not train a publishable model on these four-row files, calculate accuracy claims
from them, or present them as an operational forecast. Replace them with a small
licensed sample only after selecting and documenting a real data source.

No third-party dataset was downloaded or bundled. Before publicly publishing even
the demonstration files, choose and document the applicable redistribution license;
this README does not assign a license to the project's code or other documents.
