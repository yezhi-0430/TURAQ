/* A proposal is data. Only the explicit confirmation sends an execution request. */
(() => {
 window.describeSource=source=>source ? ({local_database:'本地数据库',python_calculation:'Python 计算'}[source.kind]||'来源类型未知')+' · 工具执行时间 '+(source.executed_at||'未知')+' · 最新交易日 '+(source.latest_trade_date||'未知')+' · '+(source.record_count??'未知')+' 条记录 · '+(source.upstream_source||'上游未知')+' · 采集时间 '+(source.collected_at||'未知')+(source.inputs_origin==='tool_arguments'?' · 输入来自工具参数':'') : '来源信息未提供；不推定数据日期。';
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
