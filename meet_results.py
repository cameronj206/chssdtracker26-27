"""Coach-only meet management. Uses existing server-side Supabase client."""
import re
from datetime import date
from decimal import Decimal
import pandas as pd
import streamlit as st

EVENTS = [('200 Medley Relay',200,True),('200 Freestyle',200,False),('200 IM',200,False),('50 Freestyle',50,False),('Diving',0,False),('100 Butterfly',100,False),('100 Freestyle',100,False),('500 Freestyle',500,False),('200 Freestyle Relay',200,True),('100 Backstroke',100,False),('100 Breaststroke',100,False),('400 Freestyle Relay',400,True)]
STATUS = ['Official','Exhibition','DQ','Scratch','No time']

def seconds(value):
    value = str(value).strip()
    if not value: return None
    if not re.fullmatch(r'\d+(?::[0-5]\d)?(?:\.\d{1,2})?',value):
        raise ValueError('Enter a time such as 28.53 or 1:02.35.')
    p=value.split(':')
    n=Decimal(p[-1])+(60*Decimal(p[0]) if len(p)==2 else 0)
    if n<=0: raise ValueError('Times must be positive.')
    return float(n)

def fmt(n):
    if n is None: return '—'
    n=float(n); m=int(n//60); s=n-m*60
    return f'{m}:{s:05.2f}' if m else f'{s:.2f}'

def fetch(client,table,columns='*',**filters):
    q=client.table(table).select(columns)
    for k,v in filters.items(): q=q.eq(k,v)
    return q.execute().data or []

def checkpoints(event_name,distance,relay):
    if not distance: return []
    if relay:
        # One split per relay leg: 50 yards for 200 relays, 100 for 400 relays.
        leg_distance=distance//4
        return [leg_distance*i for i in range(1,5)]
    return list(range(50,distance+1,50))

def parse_splits(raw,mode,marks,final):
    if not marks: return []
    vals=[seconds(v) for v in raw]
    if all(v is None for v in vals): return []
    if any(v is None for v in vals): raise ValueError('Enter all split fields, or leave every split blank.')
    cumulative=[]; running=Decimal('0')
    for v in vals:
        running=Decimal(str(v)) if mode=='Cumulative' else running+Decimal(str(v))
        cumulative.append(running)
    if any(b<=a for a,b in zip(cumulative,cumulative[1:])): raise ValueError('Cumulative splits must increase.')
    if final is not None and abs(cumulative[-1]-Decimal(str(final)))>Decimal('.02'):
        raise ValueError('The last cumulative split must match the final time.')
    return [{'distance_yards':d,'cumulative_seconds':float(c),'split_seconds':float(c-(cumulative[i-1] if i else 0))} for i,(d,c) in enumerate(zip(marks,cumulative))]

def render_private(client):
    st.subheader('Meet Results')
    st.caption('Coach-only entry. Create a roster and meet, then enter or correct event results.')
    try:
        meets=fetch(client,'swim_meets','id,name,meet_date,location,is_published')
        swimmers=fetch(client,'swim_swimmers','id,name,gender,is_active')
    except Exception as exc:
        st.error('Meet tables are unavailable. Run the SQL setup first.'); st.exception(exc); return
    with st.expander('Manage team roster'):
        with st.form('add_swimmer',clear_on_submit=True):
            name=st.text_input('Swimmer full name')
            gender=st.selectbox('Division',['Women','Men'])
            if st.form_submit_button('Add swimmer'):
                if not name.strip(): st.error('Enter a name.')
                else:
                    try:
                        client.table('swim_swimmers').insert({'name':name.strip(),'gender':gender}).execute(); st.rerun()
                    except Exception as exc: st.error(f'Could not add swimmer: {exc}')
        if swimmers: st.dataframe(pd.DataFrame(swimmers)[['name','gender','is_active']],hide_index=True,use_container_width=True)
    with st.expander('Create a meet'):
        with st.form('add_meet',clear_on_submit=True):
            meet_name=st.text_input('Meet name')
            when=st.date_input('Date',value=date.today())
            location=st.text_input('Location (optional)')
            if st.form_submit_button('Create meet'):
                if not meet_name.strip(): st.error('Enter a meet name.')
                else:
                    try:
                        client.table('swim_meets').insert({'name':meet_name.strip(),'meet_date':when.isoformat(),'location':location,'is_published':False}).execute(); st.rerun()
                    except Exception as exc: st.error(f'Could not create meet: {exc}')
    if not meets: st.info('Create a meet to begin.'); return
    meets.sort(key=lambda m:(m['meet_date'],m['id']),reverse=True)
    meet=st.selectbox('Select meet',meets,format_func=lambda m:f"{m['meet_date']} · {m['name']}")
    publish=st.checkbox('Publish results on the public website',value=meet['is_published'],key=f"publish_{meet['id']}")
    if publish!=meet['is_published']:
        try:
            client.table('swim_meets').update({'is_published':publish}).eq('id',meet['id']).execute(); st.rerun()
        except Exception as exc: st.error(f'Could not update publication: {exc}')
    division=st.radio('Division',['Women','Men'],horizontal=True)
    event=st.selectbox('Event',[e[0] for e in EVENTS])
    distance,relay=next((d,r) for n,d,r in EVENTS if n==event)
    marks=checkpoints(event,distance,relay)
    eligible=[s for s in swimmers if s['gender']==division and s['is_active']]
    existing=fetch(client,'swim_results','*',meet_id=meet['id'],gender=division,event_name=event)
    names={s['id']:s['name'] for s in swimmers}
    if existing:
        st.dataframe(pd.DataFrame([{'ID':r['id'],'Entry':r.get('relay_name') or names.get(r.get('swimmer_id'),'Unknown'),'Result':f"{r['diving_score']:.2f}" if r.get('diving_score') is not None else fmt(r['final_seconds']),'Status':r['status']} for r in existing]),hide_index=True,use_container_width=True)
    choices=['+ New result']+[f"Edit #{r['id']}: {r.get('relay_name') or names.get(r.get('swimmer_id'),'Unknown')}" for r in existing]
    selected=st.selectbox('New or edit existing result',range(len(choices)),format_func=lambda i:choices[i])
    old=existing[selected-1] if selected else None
    if old is not None:
        # Deleting the parent result cascades to its splits and relay legs.
        # Require explicit confirmation to prevent accidental removal.
        with st.expander('Delete selected relay' if relay else 'Delete selected individual result'):
            entry_label = old.get('relay_name') or names.get(old.get('swimmer_id'), 'Unknown swimmer')
            st.warning(f"This permanently deletes {entry_label}'s {event} result from {meet['name']}, including recorded splits" + (' and relay legs.' if relay else '.'))
            confirmed = st.checkbox('I understand this result will be permanently deleted', key=f"confirm_delete_result_{old['id']}")
            if st.button('Delete relay' if relay else 'Delete individual result', type='primary', disabled=not confirmed, key=f"delete_result_{old['id']}"):
                try:
                    client.table('swim_results').delete().eq('id', old['id']).eq('meet_id', meet['id']).execute()
                    st.success('Result deleted. The swimmer roster was not changed.')
                    st.rerun()
                except Exception as exc:
                    st.error(f'Could not delete result: {exc}')
    old_splits=fetch(client,'meet_splits','distance_yards,cumulative_seconds,split_seconds',result_id=old['id']) if old else []
    split_by_distance={s['distance_yards']:s for s in old_splits}
    old_legs=fetch(client,'swim_relay_legs','leg_number,swimmer_id',result_id=old['id']) if old and relay else []
    leg_by_number={l['leg_number']:l['swimmer_id'] for l in old_legs}
    if not eligible: st.warning('Add active swimmers in this division to the roster first.'); return
    count=st.number_input('Number of new results to enter',min_value=1,max_value=30,value=1,disabled=bool(old),help='For batch entry, choose + New result. Each entry has its own Save button.')
    mode=st.radio('Split entry mode',['Cumulative','Individual'],horizontal=True)
    st.caption('Individual races: 50-yard checkpoints. Relays: one split per relay leg. Splits are optional if you know only the final time.')
    for i in range(1 if old else int(count)):
        with st.expander(f"{'Edit result' if old else ('Relay' if relay else 'Swimmer')+' '+str(i+1)}",expanded=(i==0)):
            with st.form(f"meet_entry_{meet['id']}_{division}_{event}_{old['id'] if old else 'new'}_{i}_{mode}"):
                swimmer_id=None; leg_ids=[]; relay_name=None
                if relay:
                    relay_name=st.text_input('Relay label',value=(old or {}).get('relay_name') or f'{division} {event} - {i+1}')
                    cols=st.columns(4)
                    for j,col in enumerate(cols):
                        default_id=leg_by_number.get(j+1)
                        idx=next((k for k,s in enumerate(eligible) if s['id']==default_id),min(j,len(eligible)-1))
                        with col:
                            sw=st.selectbox(f'Leg {j+1}',eligible,index=idx,format_func=lambda s:s['name'])
                            leg_ids.append(sw['id'])
                else:
                    idx=next((k for k,s in enumerate(eligible) if s['id']==(old or {}).get('swimmer_id')),0)
                    sw=st.selectbox('Swimmer',eligible,index=idx,format_func=lambda s:s['name']); swimmer_id=sw['id']
                status=st.selectbox('Status',STATUS,index=STATUS.index((old or {}).get('status','Official')) if (old or {}).get('status','Official') in STATUS else 0)
                if event=='Diving':
                    score=st.number_input('Diving score',min_value=0.0,step=0.5,value=float((old or {}).get('diving_score') or 0.0),format='%.2f')
                    final_text=''; raw=[]
                else:
                    final_text=st.text_input('Final time',value=fmt(old['final_seconds']) if old and old.get('final_seconds') is not None else '',placeholder='1:52.34')
                    raw=[]
                    cols=st.columns(min(len(marks),5))
                    for j,d in enumerate(marks):
                        prior=split_by_distance.get(d)
                        value=fmt(prior['cumulative_seconds' if mode=='Cumulative' else 'split_seconds']) if prior else ''
                        with cols[j%len(cols)]: raw.append(st.text_input(f'{d} yd',value=value))
                    score=None
                if st.form_submit_button('Update result' if old else 'Save result',type='primary'):
                    try:
                        if relay and len(set(leg_ids))!=4: raise ValueError('Select four different relay swimmers.')
                        if old is None and not relay and any(r['swimmer_id']==swimmer_id for r in existing):
                            raise ValueError('This swimmer already has a result in this event. Use Edit existing result.')
                        final=seconds(final_text) if event!='Diving' else None
                        splits=parse_splits(raw,mode,marks,final) if event!='Diving' else []
                        if final is None and splits: final=splits[-1]['cumulative_seconds']
                        if status in ('Official','Exhibition') and ((event=='Diving' and score<=0) or (event!='Diving' and final is None)):
                            raise ValueError('Official/exhibition results require a time or diving score.')
                        if status in ('DQ','Scratch','No time'):
                            final=None; score=None; splits=[]
                        payload={'meet_id':meet['id'],'gender':division,'event_name':event,'swimmer_id':swimmer_id,'relay_name':relay_name,'is_relay':relay,'status':status,'final_seconds':final,'diving_score':score}
                        if old:
                            result_id=old['id']; client.table('swim_results').update(payload).eq('id',result_id).execute()
                        else:
                            result_id=client.table('swim_results').insert(payload).execute().data[0]['id']
                        # Replace splits and relay legs for edited results.
                        client.table('meet_splits').delete().eq('result_id',result_id).execute()
                        if splits: client.table('meet_splits').insert([{'result_id':result_id,**s} for s in splits]).execute()
                        client.table('swim_relay_legs').delete().eq('result_id',result_id).execute()
                        if relay: client.table('swim_relay_legs').insert([{'result_id':result_id,'leg_number':j+1,'swimmer_id':sid} for j,sid in enumerate(leg_ids)]).execute()
                        st.success('Result saved.'); st.rerun()
                    except Exception as exc: st.error(f'Could not save result: {exc}')
