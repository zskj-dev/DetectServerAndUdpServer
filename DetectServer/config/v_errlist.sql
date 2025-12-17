SELECT
  `aa`.`id` AS `id`,
  ( CASE WHEN ( `aa`.`errfrom` = '2' ) THEN '系统任务' WHEN ( `aa`.`errfrom` = '1' ) THEN '检测终端' END ) AS `errfrom`,
  `aa`.`errdatetime` AS `updatetime`,
  `dv`.`ip` AS `nvrip`,
  `aa`.`nvrport` AS `nvrport`,
  `aa`.`nvruser` AS `nvruser`,
  `aa`.`nvrpasswd` AS `nvrpasswd`,
  `aa`.`nvrchannel` AS `nvrchannel`,
  (
    CASE
        
        WHEN ( `aa`.`state` = '0' ) THEN
        '检测中' 
        WHEN ( `aa`.`state` = '1' ) THEN
        '检测正常' 
        WHEN ( `aa`.`state` = '2' ) THEN
        '检测提示' 
        WHEN ( `aa`.`state` = '3' ) THEN
        '检测告警' 
        WHEN ( `aa`.`state` = '4' ) THEN
        '图像不存在' 
        WHEN ( `aa`.`state` = '5' ) THEN
        '图像不可读' 
        WHEN ( `aa`.`state` = '6' ) THEN
        '图像为空' 
        END 
      ) AS `stateval`,
      `aa`.`state` AS `state`,
      `aa`.`errortype` AS `errortype`,
      `aa`.`errorimg` AS `errorimg`,
      `aa`.`flag` AS `flag`,
      `aa`.`gifname` AS `gifname`,
      `bb`.`dvrchannel` AS `dvrchannel`,
      `cc`.`camera_id` AS `camera_id`,
      `cc`.`camera_name` AS `camera_name`,
      `cc`.`roomid` AS `roomid`,
      `dd`.`roomname` AS `roomname`,
      `ee`.`stationname` AS `stationname`,
      (
        CASE
            
            WHEN ( `aa`.`state` = '3' ) THEN
            (
              SELECT
                `m_modelinfo`.`errtypename` 
              FROM
                `m_modelinfo` 
              WHERE
                (
                  ( `m_modelinfo`.`errtypeindex` = `aa`.`errortype` ) 
                  AND ( `m_modelinfo`.`modelid` = ( SELECT `m_model`.`id` FROM `m_model` WHERE ( `m_model`.`flag` = 1 ) ) ) 
                ) 
            ) 
            WHEN ( `aa`.`state` = '0' ) THEN
            '检测中' 
            WHEN ( `aa`.`state` = '1' ) THEN
            '无异常' ELSE '检测异常' 
            END 
          ) AS `meaning`,
          `aa`.`optflag1` AS `optflag1`,
          `aa`.`confirm` AS `confirm` 
        FROM
          (
            (
              (
                (
                  `m_dvr` `dv`
                  LEFT JOIN (
                    `m_errorinfo` `aa`
                    LEFT JOIN `m_devrunconfig` `bb` ON ( ( ( `aa`.`devid` = `bb`.`devid` ) AND ( `aa`.`nvrchannel` = `bb`.`devchannel` ) ) ) 
                  ) ON ( ( ( `dv`.`dvr_id` = `bb`.`dvrinfoid` ) AND ( `aa`.`nvrip` = `dv`.`ip` ) ) ) 
                )
                LEFT JOIN `m_camera` `cc` ON ( ( ( `bb`.`dvrinfoid` = `cc`.`dvr_id` ) AND ( `bb`.`dvrchannel` = `cc`.`channel` ) ) ) 
              )
              LEFT JOIN `m_stationroom` `dd` ON ( ( `dd`.`id` = `cc`.`roomid` ) ) 
            )
            LEFT JOIN `m_stationinfo` `ee` ON ( ( `ee`.`id` = `dd`.`stationid` ) ) 
          ) 
      ORDER BY
          `aa`.`errdatetime` DESC