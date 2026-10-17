/* A proposal is data. Only the explicit confirmation sends an execution request. */
(() => {
 window.describeAnswerSource=source=>{
  if(!source)return '';
  if(source.kind==='public_document')return (source.upstream_source||'披露资料')+(source.document_titles?.length?' · '+source.document_titles.join('、'):'')+(source.published_dates?.length?' · 发布日期 '+source.published_dates.join('、'):'')+(source.page_numbers?.length?' · PDF文件页 '+[...new Set(source.page_numbers)].join('、'):'')+({no_data:' · 未检索到资料',insufficient_data:' · 资料不足'}[source.data_status]||'');
  const name=source.upstream_source||({local_database:'本地资料',cached_catalog:'股票目录快照',python_calculation:source.inputs_origin==='tool_arguments'?'基于提供的数字':'来源未记录',online_market:'公开行情来源未记录'}[source.kind]||'来源未记录');
  return name+(source.quote_time?' · 行情时间 '+String(source.quote_time).replace('T',' '):source.latest_trade_date?' · 交易日 '+source.latest_trade_date:'')+({none:' · 不复权',qfq:' · 前复权',hfq:' · 后复权'}[source.price_adjustment]||'')+({partial:' · 部分资料未取得',insufficient_data:' · 资料不足',local_fallback:' · 采用本地已有资料',no_data:' · 该范围暂无记录'}[source.data_status]||'');
 };
 window.describeSource=source=>source ? ({local_database:'本地数据库',python_calculation:'Python 计算',online_market:source.quote_time?'在线行情报价':'在线历史行情',cached_catalog:'股票代码目录（缓存）'}[source.kind]||'来源类型未知')+' · 工具执行时间 '+(source.executed_at||'未知')+' · 本次返回数据的最新交易日 '+(source.latest_trade_date||'未知')+' · '+(source.record_count??'未知')+' 条记录 · '+(source.upstream_source||'上游未知')+' · 采集时间 '+(source.collected_at||'未知')+(source.quote_time?' · 行情观测时间 '+source.quote_time:'')+(source.inputs_origin==='tool_arguments'?' · 输入来自工具参数':source.inputs_origin==='market_data'?' · 输入来自已查询行情':'')+({local_fallback:' · 在线失败，已回退本地',no_data:' · 源未返回区间记录',partial:' · 部分失败',insufficient_data:' · 信息不足'}[source.data_status]||'')+({none:' · 不复权',qfq:' · 前复权',hfq:' · 后复权'}[source.price_adjustment]||'')+(source.warnings?.length?' · '+source.warnings.join('；'):'') : '来源信息未提供；不推定数据日期。';
 class ExecutionConfirmation {
  constructor(api,suggestion){this.api=api;this.target={kind:'execution_request',operation:suggestion.operation,watchlist_id:suggestion.watchlist_id,stock_code:suggestion.stock_code};this.state='suggested';this.error='';}
  async prepare(){
   if(this.state==='running'||this.state==='unknown'||this.state==='success')return;
   this.state='checking';
   try{
    if(this.target.operation!=='remove_watchlist_stock')throw Error('不支持此操作。');
    const groups=await this.api.request('/watchlists');this.group=groups.find(g=>g.id===this.target.watchlist_id);
    if(!this.group)throw Error('目标不在你的自选分组中。');
    const stocks=await this.api.request('/watchlists/'+this.group.id+'/stocks');this.stock=stocks.find(s=>s.symbol===this.target.stock_code);
    if(!this.stock)throw Error('该股票已不在目标分组中。');
    this.state='ready';this.error='';
   }catch(error){this.state='error';this.error=error.message;throw error;}
  }
  cancel(){if(this.state==='ready')this.state='suggested';}
  async confirm(){
   if(this.state!=='ready')return;
   this.state='running';
   try{const result=await this.api.request('/agent/actions/remove-stock',{method:'POST',body:this.target});
    this.state=result?.status==='success'?'success':'error';this.error=result?.error?.message||'服务未确认执行成功。';return result;
   }catch(error){this.state=error.unknownOutcome?'unknown':'error';this.error=error.message;}
  }
  async reconcile(){
   if(this.state!=='unknown')return;
   const stocks=await this.api.request('/watchlists/'+this.target.watchlist_id+'/stocks');this.targetPresent=stocks.some(s=>s.symbol===this.target.stock_code);
   this.error=this.targetPresent?'核对结果：股票仍在分组中；原操作结果待确认。':'核对结果：股票已不在分组中；这不能证明原请求执行成功。';
  }
 }
 window.ExecutionConfirmation=ExecutionConfirmation;
})();
