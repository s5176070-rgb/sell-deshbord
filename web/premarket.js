(function renderPremarket(){
  const pm=data.premarket;
  const signed=value=>value==null?'—':`${value>0?'+':''}${fmt(value,2)}%`;
  const quoteTime=value=>value?new Date(value).toLocaleString('he-IL',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit',timeZone:'Asia/Jerusalem'}):'לא זמין';
  if(!pm){
    $('pm-session').textContent='לא זמין';
    $('pm-fresh').textContent='לא התקבל ציטוט עדכני';
    $('pm-history-title').textContent='הקשר היסטורי אינו זמין כרגע';
    return;
  }
  $('pm-session').textContent=pm.session||'לא ידוע';
  $('pm-fresh').textContent=pm.is_stale?`ציטוט ישן · לפני ${fmt(pm.age_minutes,0)} דקות`:`עודכן לפני ${fmt(pm.age_minutes,0)} דקות`;
  $('pm-fresh').classList.toggle('stale',Boolean(pm.is_stale));
  for(const [key,id] of [['es','pm-es'],['spy','pm-spy']]){
    const value=pm[key]?.change_pct,el=$(id);el.textContent=signed(value);
    el.classList.toggle('up',value>0);el.classList.toggle('down',value<0);
    $(id+'-at').textContent=`${quoteTime(pm[key]?.at)} · שעון ישראל`;
  }
  const h=pm.historical;
  if(h){
    $('pm-history-title').textContent=h.label;
    $('pm-days').textContent=fmt(h.days,0);
    $('pm-same-day').textContent=fmt(h.same_day_drop_pct)+'%';
    $('pm-next20').textContent=fmt(h.drawdown_20d_pct)+'%';
  }else $('pm-history-title').textContent='אין מדגם היסטורי זמין';
  $('pm-source').textContent=`מקור: ${pm.source||'לא זמין'}`;
})();
