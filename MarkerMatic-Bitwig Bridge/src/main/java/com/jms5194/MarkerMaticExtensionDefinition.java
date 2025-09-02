package com.jms5194;
import java.util.UUID;

import com.bitwig.extension.api.PlatformType;
import com.bitwig.extension.controller.AutoDetectionMidiPortNamesList;
import com.bitwig.extension.controller.ControllerExtensionDefinition;
import com.bitwig.extension.controller.api.ControllerHost;

public class MarkerMaticExtensionDefinition extends ControllerExtensionDefinition
{
   private static final UUID DRIVER_ID = UUID.fromString("046f9950-6f1e-11f0-b558-0800200c9a66");
   
   public MarkerMaticExtensionDefinition()
   {
   }

   @Override
   public String getName()
   {
      return "MarkerMatic Bridge";
   }
   
   @Override
   public String getAuthor()
   {
      return "jms5194";
   }

   @Override
   public String getVersion()
   {
      return "1.0";
   }

   @Override
   public UUID getId()
   {
      return DRIVER_ID;
   }
   
   @Override
   public String getHardwareVendor()
   {
      return "jms5194";
   }
   
   @Override
   public String getHardwareModel()
   {
      return "MarkerMatic Bridge";
   }

   @Override
   public int getRequiredAPIVersion()
   {
      return 24;
   }

   @Override
   public int getNumMidiInPorts()
   {
      return 0;
   }

   @Override
   public int getNumMidiOutPorts()
   {
      return 0;
   }

   @Override
   public void listAutoDetectionMidiPortNames(final AutoDetectionMidiPortNamesList list, final PlatformType platformType)
   {
   }

   @Override
   public MarkerMaticBridgeExtension createInstance(final ControllerHost host)
   {
      return new MarkerMaticBridgeExtension(this, host);
   }
}
