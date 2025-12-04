
/etc/init.d/mysql start

nginx -t -c /etc/nginx/nginx.conf


python_num=`ps aux | grep python | wc -l`

#echo ${python_num}
if test "$python_num" -gt "1" ;then
    ps aux | grep -w python3 | awk '{print $2}' | xargs kill -9
fi

python_num=`ps aux | grep python3 | wc -l`

echo ${python_num}


python3 app.py



#nohup python3 /MonitorErrorDirFoundInfo.py &
#nohup python3 ./DetectVideoServer/app.py &


