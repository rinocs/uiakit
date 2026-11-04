from uai_worker import main


def test_busy_document_queue_does_not_starve_indexer(monkeypatch):
    calls = []

    class Worker:
        def run_once(self):
            calls.append('document')
            if calls.count('document') == 2:
                main._stop = True
            return True

    class Indexer:
        def run_once(self):
            calls.append('index')
            main._stop = True
            return True

    monkeypatch.setattr(main, '_stop', False)
    monkeypatch.setattr(main, 'configure', lambda: None)
    monkeypatch.setattr(main, 'build_worker', lambda: (Worker(), Indexer()))
    monkeypatch.setattr(main.signal, 'signal', lambda *args: None)
    monkeypatch.delenv('UAI_WORKER_ONCE', raising=False)
    main.main()
    assert calls == ['document', 'index']


def test_once_processes_only_one_job_and_falls_back_to_indexer(monkeypatch):
    monkeypatch.setattr(main, 'configure', lambda: None)
    monkeypatch.setattr(main.signal, 'signal', lambda *args: None)
    monkeypatch.setenv('UAI_WORKER_ONCE', '1')
    for has_document in (True, False):
        calls = []

        class Worker:
            def run_once(self):
                calls.append('document')
                return has_document

        class Indexer:
            def run_once(self):
                calls.append('index')
                return True

        monkeypatch.setattr(main, '_stop', False)
        monkeypatch.setattr(main, 'build_worker', lambda: (Worker(), Indexer()))
        main.main()
        assert calls == (['document'] if has_document else ['document', 'index'])
