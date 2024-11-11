from flask import Flask
import os, logging
import logging.handlers
import locate, gvi2pnx, fidfl, fidfl2, test

try:
    user = os.environ['USER']
except:
    user = 'gvi'
try:
    home = os.environ['HOME']
except:
    home = '/home/gvi'
    
LOG_FILENAME = '%s/primogvi/log/application.log' % home

handler = logging.handlers.RotatingFileHandler(
              LOG_FILENAME, maxBytes=10000000, backupCount=20)

logging.basicConfig(
    handlers = [handler],
    level=logging.DEBUG,
    format='%(filename)s (line %(lineno)d) %(levelname)s %(asctime)s  %(message)s'
   )

logging.info('----------------------')
logging.info('Server Process started')
logging.info('----------------------')
for name in os.environ:
    logging.info('%s=%s' % (name, os.environ[name]))


app = Flask(__name__)



@app.route('/plain')
def do_plain():
    return gvi2pnx.do_plain()

@app.route('/json')
def do_json():
    return gvi2pnx.do_json()



    
    
    
if __name__ == "__main__":

    app.run()
    
    
    


