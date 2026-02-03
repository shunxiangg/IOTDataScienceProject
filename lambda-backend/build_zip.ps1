Remove-Item -Recurse -Force package -ErrorAction SilentlyContinue
New-Item -ItemType Directory package | Out-Null

pip install -r requirements.txt -t package
Copy-Item lambda_function.py package\

Compress-Archive -Path package\* -DestinationPath openai_lambda.zip -Force
Write-Output "Created openai_lambda.zip"
