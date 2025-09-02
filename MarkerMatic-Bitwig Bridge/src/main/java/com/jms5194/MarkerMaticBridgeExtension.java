package com.jms5194;

import com.bitwig.extension.controller.api.*;
import com.bitwig.extension.controller.ControllerExtension;
import py4j.GatewayServer;

public class MarkerMaticBridgeExtension extends ControllerExtension {

    // Objects we want to expose to Python, accessed via getters found below.

    private Transport transport;
    private CueMarkerBank cuemarkerbank;
    private Arranger arranger;
    private CueMarker marker;

    // The object that bridges Java to Python
    private GatewayServer gatewayServer;

    protected MarkerMaticBridgeExtension(final MarkerMaticExtensionDefinition definition, final ControllerHost host) {
        super(definition, host);
    }


    @Override
    public void init() {
        final ControllerHost host = getHost();

        // Setting up API objects that we want to access from Python
        this.transport = host.createTransport();
        this.transport.isPlaying().markInterested();
        this.transport.isArrangerRecordEnabled().markInterested();

        this.arranger = host.createArranger();

        this.cuemarkerbank = this.arranger.createCueMarkerBank(512);
        this.cuemarkerbank.itemCount().markInterested();

        for (int i = 0; i < 512; i++) {
            this.cuemarkerbank.getItemAt(i).name().markInterested();
            this.cuemarkerbank.getItemAt(i).position().markInterested();
        }

        initGateway();

        host.showPopupNotification("MarkerMatic Bridge Initialized");
    }

    public String getCueMarkerInfo(int marker_num) {
        CueMarker MarkerInQuestion = this.cuemarkerbank.getItemAt(marker_num);
        String MIQName = MarkerInQuestion.name().get();
        String MIQPos = String.valueOf(MarkerInQuestion.position().getAsDouble());
        String MIQInfo = MIQName + "<> " + MIQPos;
        return MIQInfo;
    }

    public void renameMarker(int marker_num, String MarkerName) {
        CueMarker MarkerInQuestion = this.cuemarkerbank.getItemAt(marker_num);
        MarkerInQuestion.name().set(MarkerName);
    }

    public void loadPlaybackPosition(String startFromHere) {
        double newPos = Double.parseDouble(startFromHere);
        this.transport.playStartPosition().set(newPos);
    }

    // Getters are needed, even though the member variables are exposed in Python.
    // If you ask for the members directly, you will not get the methods of that member. Asking for the members
    // via getters seem to solve this.

    public CueMarkerBank getCueMarkerBank() {
        return cuemarkerbank;
    }

    public Transport getTransport() {
        return this.transport;
    }

    public CueMarker getCueMarker() { return this.marker;}

    public Arranger getArranger() {
        return arranger;
    }


    // Initialize the GatewayServer with a pointer to this class.
    void initGateway() {
        gatewayServer = new GatewayServer(this);

        // This part is not thoroughly tested.
        try {
            gatewayServer.start();
            getHost().println("Gateway Server Started");
        } catch (py4j.Py4JNetworkException e) {
            getHost().println("Gateway Server already running.");
        }
    }

    @Override
    public void exit() {
        gatewayServer.shutdown();
        getHost().showPopupNotification("MarkerMatic Bridge Exited");
    }

    @Override
    public void flush() {
        // TODO Send any updates you need here.
    }


}
