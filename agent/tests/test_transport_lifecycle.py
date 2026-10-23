"""Streams must unwind before their owner closes any transport descriptors."""
import asyncio
import sys
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'web-redesign')]
import control
from agent import models,store

class TransportLifecycleTests(unittest.TestCase):
    def execute(self,mode='complete',on_progress=None):
        steps=[];owner=threading.get_ident();requests=[];remaining=[]
        receipt={'id':'fixture','status':'completed','usage':{'input_tokens':10,'output_tokens':3},'output':[]}
        class Stream:
            def __aiter__(self):return self.read()
            async def read(self):
                try:
                    steps.append(('reading',threading.get_ident()))
                    if mode=='silent_body':await asyncio.sleep(10)
                    if mode=='broken':raise OSError('Synthetic stream error')
                    yield types.SimpleNamespace(type='response.output_text.delta',delta='OK')
                    yield types.SimpleNamespace(type='response.completed',response=types.SimpleNamespace(model_dump=lambda **kw:receipt))
                    if mode=='backpressure':
                        for _ in range(500):yield types.SimpleNamespace(type='response.output_text.delta',delta='extra')
                finally:steps.append(('read_unwound',threading.get_ident()))
            async def close(self):
                steps.append(('stream_close',threading.get_ident()))
        class Client:
            def __init__(self,**kw):self.responses=self
            async def create(self,**kw):
                requests.append(kw)
                try:
                    if mode=='silent_headers':await asyncio.sleep(10)
                    return Stream()
                finally:steps.append(('create_unwound',threading.get_ident()))
            async def close(self):
                remaining.extend(t for t in asyncio.all_tasks() if t.get_name()=='sensys-response-reader' and not t.done())
                steps.append(('client_close',threading.get_ident()))
        with patch('openai.AsyncOpenAI',Client),patch.object(control,'public_address'),patch.object(control,'crypt',return_value='fixture'),patch.object(store,'settings',return_value={'api_timeout_seconds':10}):
            try:
                result=models.response({'secret':'fixture','base_url':'https://example.com/v1','model':'example-model'},'fixture instructions',[{'role':'user','content':'fixture'}],[],'medium',100,on_progress)
            finally:
                self.assertEqual(steps[-1][0],'client_close')
                self.assertTrue(all(ident==owner for _,ident in steps))
                self.assertEqual(remaining,[])
                self.assertEqual(sum(name=='client_close' for name,_ in steps),1)
        self.assertEqual(result,receipt)
        self.assertEqual(requests[0]['model'],'example-model')
        self.assertTrue(requests[0]['stream'])
        return steps

    def test_normal_completion_closes_after_reader_unwinds(self):
        steps=self.execute()
        self.assertLess([x[0] for x in steps].index('stream_close'),[x[0] for x in steps].index('client_close'))

    def test_silent_headers_cancel_without_live_reader(self):
        def stop(*args):raise InterruptedError('fixture stop')
        start=time.monotonic()
        with self.assertRaisesRegex(InterruptedError,'fixture stop'):self.execute('silent_headers',stop)
        self.assertLess(time.monotonic()-start,2)

    def test_silent_body_deadline_unwinds_before_close(self):
        def stop(*args):raise TimeoutError('fixture deadline')
        start=time.monotonic()
        with self.assertRaisesRegex(TimeoutError,'fixture deadline'):self.execute('silent_body',stop)
        self.assertLess(time.monotonic()-start,2)

    def test_full_queue_does_not_deadlock_cleanup(self):
        self.execute('backpressure')

    def test_provider_error_unwinds_and_is_not_retried(self):
        with self.assertRaisesRegex(OSError,'Synthetic stream error'):self.execute('broken')
