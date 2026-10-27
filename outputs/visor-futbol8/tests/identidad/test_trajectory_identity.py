"""Regressions for persistent identities across turns, aliases and true cuts."""
import unittest, copy
from f8.identidad.trajectory_identity import stabilize
from f8.acciones.contactos import infer_possession
from f8.acciones.sequence_engine import sequence_actions


def box(tid=1, pid='orange-41', x=100, method='jersey_vote', segment='s1', kit='orange'):
    return {'id': tid, 'player_id': pid, 'segment_id': segment, 'kit': kit,
            'box': [x-20, 20, x+20, 100], 'confidence': .9, 'position': None,
            'identity': {'method': method, 'state': 'accepted' if pid else 'unknown'}}


def rows(boxes):
    return [{'frame': i*3, 'time': round(i*.1, 4), 'tracks': bs, 'ball': None} for i, bs in enumerate(boxes)]


class ContextIdentityTests(unittest.TestCase):
    def test_turn_and_weak_frame_keep_name(self):
        a=box(); b=box(pid=None, method='unknown'); b['identity']['proposal']={'number':7,'similarity':.95}
        rs=rows([[a],[b],[box()]]); contexts,q=stabilize(rs)
        self.assertEqual([r['tracks'][0]['player_id'] for r in rs], ['orange-41']*3)
        self.assertEqual(len(contexts),1); self.assertEqual(q['identity_changes_inside_context'],0)
    def test_later_dorsal_labels_the_whole_continuous_person(self):
        rs=rows([[box(pid=None,method='unknown')],[box(method='jersey_vote')]])
        stabilize(rs); self.assertEqual(rs[0]['tracks'][0]['player_id'],'orange-41')
    def test_strong_dorsal_corrects_weak_appearance_in_both_directions(self):
        rs=rows([[box(pid='orange-7',method='calibrated_appearance')],[box()]])
        stabilize(rs); self.assertEqual([r['tracks'][0]['player_id'] for r in rs],['orange-41']*2)
    def test_conflicting_hard_dorsal_opens_a_new_context(self):
        rs=rows([[box()],[box(pid='orange-7',segment='s2')]])
        contexts,q=stabilize(rs); self.assertEqual(len(contexts),2)
        self.assertEqual([r['tracks'][0]['player_id'] for r in rs],['orange-41','orange-7'])
    def test_tracker_cut_is_respected_even_when_boxes_are_near(self):
        rs=rows([[box()],[box(pid=None,method='unknown',segment='s2')]])
        contexts,q=stabilize(rs,cuts=[{'track_id':1,'time':.05}]); self.assertEqual(len(contexts),2)
        self.assertIsNone(rs[1]['tracks'][0]['player_id'])
    def test_dense_unambiguous_motion_can_reconcile_an_old_sparse_cut(self):
        rs=rows([[box()],[box(pid=None,method='unknown',segment='s2',x=103)]])
        cs,q=stabilize(rs,cuts=[{'track_id':1,'time':.05,'reason':'Discontinuidad de trayectoria'}])
        self.assertEqual(len(cs),1);self.assertEqual(rs[1]['tracks'][0]['player_id'],'orange-41')
    def test_crowded_old_cut_still_stops_identity_propagation(self):
        rs=rows([[box()],[box(pid=None,method='unknown',segment='s2',x=103),box(tid=2,pid=None,x=110)]])
        cs,q=stabilize(rs,cuts=[{'track_id':1,'time':.05,'reason':'Discontinuidad de trayectoria'}])
        self.assertIsNone(rs[1]['tracks'][0]['player_id'])
    def test_large_physical_jump_does_not_inherit_name(self):
        rs=rows([[box()],[box(pid=None,method='unknown',x=600)]])
        contexts,q=stabilize(rs); self.assertEqual(len(contexts),2); self.assertIsNone(rs[-1]['tracks'][0]['player_id'])
    def test_unique_intermediate_dense_box_keeps_the_context(self):
        rs=rows([[box()],[box(tid='D3-0',pid=None,method='unknown',segment=None,x=103)],[box(x=106)]])
        contexts,q=stabilize(rs); self.assertEqual(len(contexts),1)
        self.assertEqual([r['tracks'][0]['player_id'] for r in rs],['orange-41']*3); self.assertEqual(q['physical_alias_links'],1)
    def test_two_simultaneous_people_are_never_aliases(self):
        rs=rows([[box(),box(tid='D0-0',pid=None,x=102)],[box(),box(tid='D3-0',pid=None,x=103)]])
        contexts,q=stabilize(rs); self.assertTrue(all(len({b['person_track_id'] for b in r['tracks']})==len(r['tracks']) for r in rs))
        self.assertTrue(all(r['tracks'][1]['player_id'] is None for r in rs))
    def test_duplicate_claim_is_resolved_for_the_whole_trajectory(self):
        weak=box(tid=2,x=250,method='calibrated_appearance',segment='s2')
        rs=rows([[box(),copy.deepcopy(weak)],[box(pid=None,method='unknown'),copy.deepcopy(weak)],[box(),copy.deepcopy(weak)]])
        contexts,q=stabilize(rs)
        self.assertTrue(all(r['tracks'][0]['player_id']=='orange-41' and r['tracks'][1]['player_id'] is None for r in rs))
        self.assertEqual(q['competing_trajectories_rejected'],1)
    def test_no_accepted_anchor_does_not_promote_a_proposal(self):
        b=box(pid=None,method='unknown'); b['identity']['proposal']={'number':41,'similarity':.99}
        rs=rows([[b]]); stabilize(rs); self.assertIsNone(b['player_id'])
    def test_uniform_roles_never_exchange(self):
        rs=rows([[box()],[box(pid='orange-41',kit='keeper')]])
        stabilize(rs); self.assertEqual(rs[-1]['tracks'][0]['player_id'],'orange-41'); self.assertEqual(rs[-1]['tracks'][0]['kit'],'orange')
        rs=rows([[box(pid='orange-41',kit='keeper')]]); stabilize(rs); self.assertIsNone(rs[0]['tracks'][0]['player_id'])
    def test_manual_rejected_interval_is_not_filled_from_neighbours(self):
        bs=[box(),box(pid=None,method='manual_review'),box()]; bs[1]['identity']['state']='rejected'
        rs=rows([[b] for b in bs]); stabilize(rs,reviews=[{'track_id':1,'start':.1,'end':.1,'decision':'rejected','item_id':'r'}])
        self.assertEqual([r['tracks'][0]['player_id'] for r in rs],['orange-41',None,'orange-41'])
    def test_reverse_seek_and_repeated_execution_do_not_change_results(self):
        rs=rows([[box()],[box(tid='D3-0',pid=None,method='unknown',segment=None)],[box()]])
        stabilize(rs); expected=[(b['person_track_id'],b['player_id']) for r in rs for b in r['tracks']]
        stabilize(rs); self.assertEqual([(b['person_track_id'],b['player_id']) for r in rs for b in r['tracks']],expected)
        self.assertEqual([(b['person_track_id'],b['player_id']) for r in reversed(rs) for b in r['tracks']],list(reversed(expected)))

class ContextReviewTests(unittest.TestCase):
    def test_context_review_corrects_alias_boxes_statistics_and_action(self):
        import tempfile, json, shutil
        from pathlib import Path
        from f8.plataforma.server import App, ROOT
        from f8.publicacion.analytics_v3 import profiles_for
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'data').mkdir();(root/'automatic/chunks').mkdir(parents=True)
            shutil.copyfile(ROOT/'plantilla.json',root/'plantilla.json')
            def write(name,value):(root/(name+'.json')).write_text(json.dumps(value),encoding='utf8')
            rs=rows([[box(),box(tid=2,pid='orange-12',x=300,segment='s2')],
                     [box(tid='D3-0',pid=None,method='unknown',segment=None),box(tid=2,pid='orange-12',x=300,segment='s2')],
                     [box(),box(tid=2,pid='orange-12',x=300,segment='s2')]])
            cs,q=stabilize(rs);context=rs[0]['tracks'][0]['person_track_id']
            events=[{'id':'e','kind':'pass','time':.1,'source_track':'D3-0','target_track':2,'player_id':'orange-41','receiver_id':'orange-12','state':'estimated','outcome':'complete','sequence':{'source_context_id':context,'reception_time':.2}}]
            write('data/metadata',{'duration':10});write('automatic/review-manifest',{'source_key':'fixture'});write('automatic/quality',{'version':7});write('automatic/chunks/000',rs)
            write('automatic/actions',events);write('automatic/lineup',{});write('automatic/identity-segments',[]);write('automatic/memory-quality',{})
            roster=json.loads((root/'plantilla.json').read_text())['players'];write('automatic/profiles',profiles_for(rs,events,roster,10))
            write('automatic/uncertainties',[{'id':'identity-'+context,'category':'identity','track_id':1,'context_id':context,'start':0,'end':.2,'player_id':'orange-41','time':0}])
            app=App(root);app.review_engine.save('identity-'+context,{'source_key':'fixture','decision':'corrected','data':{'player_id':'orange-7'}})
            out=app.review_engine.effective()
            self.assertEqual([r['tracks'][0]['player_id'] for r in out['records']],['orange-7']*3)
            self.assertEqual(out['actions'][0]['player_id'],'orange-7')
            self.assertEqual(next(p for p in out['profiles'] if p['id']=='orange-7')['metrics']['passes']['value'],1)
            self.assertEqual(next(p for p in out['profiles'] if p['id']=='orange-41')['samples'],0)
    def test_context_prevents_an_alias_from_passing_to_itself(self):
        from f8.acciones.pass_engine import contact_episodes
        rs=rows([[box()],[box(tid='D3-0',pid=None,method='unknown',segment=None)],[box()]])
        stabilize(rs)
        for r in rs:
            b=r['tracks'][0];r['ball']={'center':[100,100],'confidence':.9,'position':None};r['possession']={'track_id':b['id'],'distance':.1}
        self.assertEqual(len(contact_episodes(rs,True)),1)

if __name__=='__main__':unittest.main()
