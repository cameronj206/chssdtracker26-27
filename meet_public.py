"""Read-only meet results viewer. Uses the public anonymous Supabase client."""
import pandas as pd
import streamlit as st

def fmt(value):
    if value is None: return '—'
    n=float(value); m=int(n//60); s=n-m*60
    return f'{m}:{s:05.2f}' if m else f'{s:.2f}'

def render_public(client):
    st.subheader('Meet Results')
    try:
        meets=client.table('swim_meets').select('id,name,meet_date,location').order('meet_date',desc=True).execute().data or []
        if not meets: st.info('No meet results have been published yet.'); return
        meet=st.selectbox('Select meet',meets,format_func=lambda m:f"{m['meet_date']} · {m['name']}")
        results=client.table('swim_results').select('id,gender,event_name,swimmer_id,relay_name,is_relay,status,final_seconds,diving_score').eq('meet_id',meet['id']).execute().data or []
        if not results: st.info('No results for this meet yet.'); return
        division=st.radio('Division',['Women','Men'],horizontal=True)
        standard=['200 Medley Relay','200 Freestyle','200 IM','50 Freestyle','Diving','100 Butterfly','100 Freestyle','500 Freestyle','200 Freestyle Relay','100 Backstroke','100 Breaststroke','400 Freestyle Relay']
        events=[e for e in standard if any(r['event_name']==e and r['gender']==division for r in results)]
        if not events: st.info('No results in this division.'); return
        event=st.selectbox('Event',events)
        selected=[r for r in results if r['gender']==division and r['event_name']==event]
        swimmers=client.table('swim_swimmers').select('id,name').execute().data or []
        names={s['id']:s['name'] for s in swimmers}
        data=[]
        for r in selected:
            splits=client.table('meet_splits').select('distance_yards,cumulative_seconds,split_seconds').eq('result_id',r['id']).order('distance_yards').execute().data or []
            label=r['relay_name'] if r['is_relay'] else names.get(r['swimmer_id'],'Unknown')
            if r['is_relay']:
                legs=client.table('swim_relay_legs').select('leg_number,swimmer_id').eq('result_id',r['id']).order('leg_number').execute().data or []
                label=f"{label} ({', '.join(names.get(l['swimmer_id'],'Unknown') for l in legs)})"
            result=f"{float(r['diving_score']):.2f} points" if r.get('diving_score') is not None else fmt(r['final_seconds'])
            data.append({'Swimmer / relay':label,'Result':result,'Status':r['status'],'Splits':', '.join(f"{s['distance_yards']}: {fmt(s['cumulative_seconds'])} ({fmt(s['split_seconds'])})" for s in splits)})
        st.dataframe(pd.DataFrame(data),hide_index=True,use_container_width=True)
        st.caption('Splits: distance, cumulative time (segment time). Relay checkpoints represent complete relay legs.')
    except Exception as exc:
        st.error('Meet results could not be loaded. Verify the database tables and public read policies.'); st.exception(exc)
