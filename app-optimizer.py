import json
import subprocess

from flask import Flask, render_template, request

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def index():
    result = None
    if request.method == 'POST':
        salary_cap = request.form.get('salary_cap')
        try:
            # Call the optimize_roster.py script with the salary cap
            output = subprocess.check_output(['python3', 'optimize_roster.py', '--salary-cap', salary_cap])
            result = output.decode('utf-8')  # Decode the output to a string
        except subprocess.CalledProcessError as e:
            result = f"Error: {e.output.decode('utf-8')}"
    
    return render_template('optimizer.html', result=result)

if __name__ == '__main__':
    app.run(debug=True)
