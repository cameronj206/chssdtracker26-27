"""Reusable, read-only meet results display for both Streamlit apps."""
import streamlit as st

EVENTS = ['200 Medley Relay','200 Freestyle','200 IM','50 Freestyle','Diving','100 Butterfly','100 Freestyle','500 Freestyle','200 Freestyle Relay','100 Backstroke','100 Breaststroke','400 Freestyle Relay']

def fmt(value):
    if value is None: return '—'
    n = float(value)
    minutes = int(n // 60)
    return f'{minutes}:{n-minutes*60:05.2f}' if minutes else f'{n:.2f}'

def _rows(client, table, columns, ids, foreign_key):
    if not ids: return []
    return client.table(table).select(columns).in_(foreign_key, ids).execute().data or []

def render_results(client, meet=None, public=True, key_prefix='public'):
    """Display results by event or swimmer, with expandable individual/relay splits."""
    try:
        if meet is None:
            meets = client.table('swim_meets').select('id,name,meet_date,location').order('meet_date', desc=True).execute().data or []
            if not meets:
                st.info('No published meet results yet.'); return
            meet = st.selectbox('Select meet', meets, format_func=lambda m: f"{m['meet_date']} · {m['name']}", key=f'{key_prefix}_meet')
        results = client.table('swim_results').select('id,gender,event_name,swimmer_id,relay_name,is_relay,status,final_seconds,diving_score').eq('meet_id',meet['id']).execute().data or []
        if not results:
            st.info('No results have been entered for this meet.'); return
        ids = [r['id'] for r in results]
        splits = _rows(client, 'meet_splits', 'result_id,distance_yards,cumulative_seconds,split_seconds', ids, 'result_id')
        legs = _rows(client, 'swim_relay_legs', 'result_id,leg_number,swimmer_id', ids, 'result_id')
        swimmer_ids = set(r['swimmer_id'] for r in results if r.get('swimmer_id')) | set(l['swimmer_id'] for l in legs)
        swimmers = _rows(client, 'swim_swimmers', 'id,name,gender', list(swimmer_ids), 'id')
        names = {s['id']:s['name'] for s in swimmers}
        split_map = {}
        leg_map = {}
        for s in splits: split_map.setdefault(s['result_id'], []).append(s)
        for l in legs: leg_map.setdefault(l['result_id'], []).append(l)
        for v in split_map.values(): v.sort(key=lambda x:x['distance_yards'])
        for v in leg_map.values(): v.sort(key=lambda x:x['leg_number'])

        division = st.radio('Division', ['Women','Men'], horizontal=True, key=f'{key_prefix}_division')
        division_results = [r for r in results if r['gender']==division]
        if not division_results:
            st.info('No results for this division.'); return
        view = st.radio('View results', ['By Event','By Swimmer'], horizontal=True, key=f'{key_prefix}_view')
        participating_ids = set()
        for r in division_results:
            if r.get('swimmer_id'): participating_ids.add(r['swimmer_id'])
            participating_ids.update(l['swimmer_id'] for l in leg_map.get(r['id'], []))
        options = sorted(participating_ids, key=lambda sid:(names.get(sid,'').casefold(),sid))
        selected_id = st.selectbox('Filter by swimmer', [None]+options,
            format_func=lambda sid:'All swimmers' if sid is None else names.get(sid,'Unknown swimmer'),
            key=f'{key_prefix}_swimmer')
        filtered = [r for r in division_results if selected_id is None or r.get('swimmer_id')==selected_id or any(l['swimmer_id']==selected_id for l in leg_map.get(r['id'],[]))]
        if not filtered:
            st.info('No results match this swimmer.'); return
        if view == 'By Event':
            available = [e for e in EVENTS if any(r['event_name']==e for r in filtered)]
            available += sorted({r['event_name'] for r in filtered}-set(available))
            chosen = st.selectbox('Event', ['All events']+available, key=f'{key_prefix}_event')
            if chosen != 'All events': filtered = [r for r in filtered if r['event_name']==chosen]
            groups = [(e,[r for r in filtered if r['event_name']==e]) for e in available if any(r['event_name']==e for r in filtered)]
        else:
            # When viewing by swimmer, select a specific swimmer so relays appear under their profile.
            if selected_id is None:
                st.caption('Select a swimmer above to see their individual events and relay appearances together.')
                groups = [('All results', filtered)]
            else:
                groups = [(names.get(selected_id,'Swimmer'),filtered)]
        st.caption(f'{len(filtered)} result(s) shown · Select a result to expand its splits.')
        for group_name, group_results in groups:
            st.markdown(f'#### {group_name}')
            for r in group_results:
                rid = r['id']
                label = (r.get('relay_name') or 'Relay') if r['is_relay'] else names.get(r.get('swimmer_id'),'Unknown swimmer')
                if view == 'By Swimmer': label = f"{r['event_name']} · {label}" if r['is_relay'] else r['event_name']
                result = f"{float(r['diving_score']):.2f} points" if r.get('diving_score') is not None else fmt(r.get('final_seconds'))
                with st.expander(f"{label}  |  {result}  |  {r['status']}", expanded=False):
                    if r['is_relay']:
                        st.markdown('**Relay lineup and leg splits**')
                        leg_rows = leg_map.get(rid,[])
                        split_rows = split_map.get(rid,[])
                        for j,l in enumerate(leg_rows):
                            s = split_rows[j] if j < len(split_rows) else None
                            text = f"Leg {l['leg_number']}: **{names.get(l['swimmer_id'],'Unknown swimmer')}**"
                            if s: text += f" · {s['distance_yards']} yd cumulative: **{fmt(s['cumulative_seconds'])}** · leg: **{fmt(s['split_seconds'])}**"
                            st.markdown(text)
                        if not leg_rows: st.caption('Relay lineup not recorded.')
                    elif r['event_name']=='Diving':
                        st.metric('Diving score',result)
                    if not r['is_relay']:
                        split_rows = split_map.get(rid,[])
                        if split_rows:
                            st.markdown('**Splits**')
                            for s in split_rows:
                                c1,c2,c3 = st.columns([1,2,2])
                                c1.write(f"{s['distance_yards']} yd")
                                c2.write(f"Cumulative: **{fmt(s['cumulative_seconds'])}**")
                                c3.write(f"Length: **{fmt(s['split_seconds'])}**")
                        elif r['event_name']!='Diving': st.caption('No splits recorded.')
                    if not public: st.caption('To edit or delete this result, use the result-entry controls below.')
    except Exception as exc:
        st.error('Meet results could not be loaded. Check the meet tables and database permissions.')
        st.exception(exc)

def render_public(client):
    st.subheader('Meet Results')
    render_results(client, public=True, key_prefix='public_results')
